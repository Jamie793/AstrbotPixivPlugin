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


class MiscService(BaseService):
    def admin_mark(self, key: str) -> str:
        return " [Admin]" if self.cfg().get(key, True) else ""

    def build_help_text(self) -> str:
        return build_pixivc_help_text(self.admin_mark)

    async def pixiv_autocomplete(self, word: str):
        api = await self.api()
        word = str(word or "").strip()
        if not word:
            return []
        params = {"word": word, "merge_plain_keyword_results": "true"}
        urls = [
            "https://app-api.pixiv.net/v2/search/autocomplete",
            "https://app-api.pixiv.net/v1/search/autocomplete",
        ]
        last_error = None
        for url in urls:
            resp = await self.api_no_auth_requests_call("GET", url, params=params)
            status = getattr(resp, "status_code", 0)
            if status == 404:
                last_error = f"HTTP 404: {url}"
                continue
            if self._looks_auth_failed(resp=resp):
                raise RuntimeError(getattr(resp, "text", "")[:300])
            if status >= 400:
                raise RuntimeError(getattr(resp, "text", "")[:300])
            api = await self.api()
            data = await asyncio.to_thread(api.parse_result, resp)
            if not isinstance(data, dict):
                raise RuntimeError(f"Pixiv 自动补全接口返回异常：HTTP {status}")
            tags = data.get("tags", [])
            if not isinstance(tags, list):
                return []
            return tags
        raise RuntimeError(last_error or "Pixiv 自动补全接口不可用")

    def format_autocomplete(self, tags, limit=20):
        lines = []
        for i, tag in enumerate(tags[:limit], 1):
            if isinstance(tag, str):
                name = tag
                translated = ""
                r18 = False
            elif isinstance(tag, dict):
                name = str(tag.get("name") or tag.get("tag") or tag.get("word") or "").strip()
                translated = str(tag.get("translated_name") or tag.get("translation") or "").strip()
                r18 = bool(tag.get("is_r18") or tag.get("isR18") or tag.get("r18"))
            else:
                continue
            if not name:
                continue
            extra = []
            if translated:
                extra.append(translated)
            if r18:
                extra.append("R18")
            suffix = f"（{'，'.join(extra)}）" if extra else ""
            lines.append(f"{i}. {name}{suffix}")
        return "Pixivc 自动补全：\n" + "\n".join(lines) if lines else "没有找到自动补全结果。"
