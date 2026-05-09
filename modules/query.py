import asyncio
import base64
import html
import json
import os
import re
import secrets
import shutil
import string
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, File, Image, Node, Nodes, Plain
from pixivpy3 import AppPixivAPI, ByPassSniApi

from .base import BaseService

try:
    import pyzipper
except Exception:
    pyzipper = None

from .paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR, R18_WHITELIST_FILE, LAST_ZIP_FILE, LAST_ITEMS_FILE, TOKEN_STATE_FILE, OAUTH_STATE_FILE, OWNER_QQ, PLUGIN_DIR
from .errors import PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE, PixivRefreshTokenInvalidError
from .help import build_help_text as build_pixivc_help_text
from .oauth import generate_login_url, exchange_token, token_parts
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)


class QueryService(BaseService):
    def parse_query_count(self, raw: str):
        c = self.cfg()
        text = (raw or "").strip()
        self._current_start_page_override = None
        self._last_count_limit_notice = ""
        page = None
        raw_count_match = re.search(r"(?:^|\s)n(\d+)(?=\s|$)", text, flags=re.IGNORECASE)
        raw_count = int(raw_count_match.group(1)) if raw_count_match else None

        # 只支持 p3 这种页码格式，可放在参数任意位置。
        # page=3 / p=3 / 第3页 / 末尾裸数字页数等写法不再支持，避免和 n3 数量格式混淆。
        m = re.search(r"(?:^|\s)p(\d+)(?=\s|$)", text, flags=re.IGNORECASE)
        if m:
            page = max(1, int(m.group(1)))
            text = (text[:m.start()] + " " + text[m.end():]).strip()

        self._current_search_max_depth_override = None
        m_depth = re.search(r"(?:^|\s)m(\d+)(?=\s|$)", text, flags=re.IGNORECASE)
        if m_depth:
            self._current_search_max_depth_override = max(1, int(m_depth.group(1)))
            text = (text[:m_depth.start()] + " " + text[m_depth.end():]).strip()

        self._current_start_page_override = page
        q, count = parse_count_arg(text, c["default_count"], c["max_count"])
        if raw_count is not None and raw_count > c["max_count"]:
            self._last_count_limit_notice = f"请求数量 n{raw_count} 超过 max_count={c['max_count']}，实际按 n{count} 处理。"
        return q, count

    def parse_query_count_tags(self, raw: str):
        text = (raw or "").strip()
        tags = []
        # 只支持 t标签1,标签2 这种附加 tag 筛选格式，可放在参数任意位置。
        # 裸逗号列表不再作为筛选 tag 解析，避免和关键词/标签查询本身混淆。
        m = re.search(r"(?:^|\s)t([^\s]+)(?=\s|$)", text, flags=re.IGNORECASE)
        if m:
            tags = split_terms(m.group(1))
            text = (text[:m.start()] + " " + text[m.end():]).strip()
        q, count = self.parse_query_count(text)
        return q, count, tags

    def split_include_exclude_tags(self, tag_terms):
        include = []
        exclude = []
        for x in (tag_terms or []):
            text = str(x).strip()
            if not text:
                continue
            if text.startswith("-") and len(text) > 1:
                exclude.append(text[1:].strip())
            else:
                include.append(text)
        return include, exclude

    def match_tag_filter(self, item, tag_terms) -> bool:
        include_raw, exclude_raw = self.split_include_exclude_tags(tag_terms)
        include = [str(x).strip().lower() for x in include_raw if str(x).strip()]
        exclude = [str(x).strip().lower() for x in exclude_raw if str(x).strip()]
        if not include and not exclude:
            return True
        tags = [str(x).strip().lower() for x in tags_text(item) if str(x).strip()]
        for term in include:
            if term not in tags:
                return False
        for term in exclude:
            if term in tags:
                return False
        return True

    def merge_tag_filters(self, *groups):
        out = []
        for group in groups:
            if not group:
                continue
            if isinstance(group, str):
                vals = split_terms(group)
            else:
                vals = list(group)
            for x in vals:
                x = str(x).strip()
                if x and x not in out:
                    out.append(x)
        return out

    def effective_search_max_depth(self):
        override = getattr(self, "_current_search_max_depth_override", None)
        if override is not None:
            return max(1, int(override))
        return max(1, int(self.cfg()["search_max_depth"]))

    def effective_start_page(self):
        if self._current_start_page_override is not None:
            return max(1, int(self._current_start_page_override))
        return 1

    def set_collect_end_reason(self, reason: str):
        self._last_collect_end_reason = reason or "未知原因"

    def collect_end_reason_text(self):
        return str(getattr(self, "_last_collect_end_reason", "未知原因") or "未知原因")

    def debug_resp_keys(self, resp):
        if isinstance(resp, dict):
            return ",".join(list(resp.keys())[:20])
        try:
            if hasattr(resp, "keys"):
                return ",".join(list(resp.keys())[:20])
        except Exception:
            pass
        return type(resp).__name__

    def set_debug_info(self, title, resp=None, raw_count=0, kept_count=0, reasons=None):
        reasons = reasons or {}
        self._last_debug = (
            f"调试信息：{title}\n"
            f"API字段：{self.debug_resp_keys(resp)}\n"
            f"提取数量：{raw_count}\n"
            f"过滤后数量：{kept_count}\n"
            f"过滤原因：r18={reasons.get('r18',0)}，ai={reasons.get('ai',0)}，收藏={reasons.get('bookmarks',0)}，浏览={reasons.get('views',0)}，点赞={reasons.get('likes',0)}，tag={reasons.get('tag',0)}"
        )

    def and_match(self, item, terms, mode="key"):
        if not terms:
            return True
        if mode == "tag":
            hay = " ".join(tags_text(item)).lower()
        else:
            hay = searchable_text(item)
        return all(t.lower() in hay for t in terms)
