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

try:
    import pyzipper
except Exception:
    pyzipper = None

try:
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
except ImportError:
    from modules.paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR, R18_WHITELIST_FILE, LAST_ZIP_FILE, LAST_ITEMS_FILE, TOKEN_STATE_FILE, OAUTH_STATE_FILE, OWNER_QQ, PLUGIN_DIR
    from modules.errors import PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE, PixivRefreshTokenInvalidError
    from modules.help import build_help_text as build_pixivc_help_text
    from modules.oauth import generate_login_url, exchange_token, token_parts
    from modules.pixiv_utils import (
        build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
        getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
        read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
        to_int, unique_items, user_info, write_json,
    )


class NovelMixin:
    async def fetch_novel_text(self, novel_id):
        api = await self.api()
        try:
            resp = await self.api_call("novel_text", int(novel_id))
            text = getv(resp, "novel_text", "") or getv(resp, "text", "") or ""
            return str(text)
        except Exception as e:
            logger.warning(f"pixivc novel text failed {novel_id}: {e}")
            return ""

    async def run_novel_job(self, event, label, collector):
        if not self.cfg()["novel_enabled"]:
            yield event.plain_result("小说功能未启用。")
            return
        if self._task_lock.locked():
            yield event.plain_result("已有 Pixiv 爬取任务正在执行，请稍后再试。")
            return
        async with self._task_lock:
            c = self.cfg()
            c["download_dir"].mkdir(parents=True, exist_ok=True)
            self._current_allow_r18 = self.allow_r18_for_event(event)
            try:
                for attempt in range(2):
                    try:
                        if attempt == 0:
                            yield event.plain_result(f"开始爬取 Pixiv 小说：{label}。")
                        else:
                            logger.info("Pixivc 已静默刷新 access token，正在自动重试本次小说命令。")
                        items = await collector()
                        if not items:
                            yield event.plain_result("没有找到符合条件的小说，可能是过滤条件过严或关键词无结果。" + ("\n" + self._last_debug if self._last_debug else ""))
                            return
                        self.save_last_items(event, items, label, "novel")
                        infos = await self.build_novel_preview_infos(items)
                        yield event.plain_result(f"小说处理完成：{len(items)} 篇，正在发送合并转发预览。需要小说 ZIP 请发送 /pixivc_get_zip")
                        async for r in self.send_forward(event, [], novel_infos=infos if c["include_novel_info"] else ["小说信息已按配置隐藏"]):
                            yield r
                        return
                    except PixivRefreshTokenInvalidError as e:
                        yield event.plain_result(str(e))
                        return
                    except Exception as e:
                        if attempt == 0 and self._looks_auth_failed(exc=e):
                            await self.refresh_api_silent()
                            continue
                        logger.error(f"pixivc novel job failed: {e}", exc_info=True)
                        yield event.plain_result(f"小说爬取失败：{e}")
                        return
            finally:
                self._current_allow_r18 = None

    async def collect_paginated_novel(self, method_name: str, count: int, *args, tag_terms=None, **kwargs):
        self._last_requested_count = count
        api = await self.api()
        c = self.cfg()
        items = []
        next_qs = None
        max_pages = self.effective_search_max_depth()
        start_page = self.effective_start_page()
        for page in range(max_pages + start_page - 1):
            if next_qs:
                resp = await self.api_call(method_name, **next_qs)
            else:
                resp = await self.api_call(method_name, *args, **kwargs)
            current_page = page + 1
            if current_page >= start_page:
                raw_batch = extract_items(resp, "novel")
                reasons = {"r18": 0, "ai": 0, "bookmarks": 0, "views": 0, "likes": 0, "tag": 0}
                batch = []
                for x in raw_batch:
                    reason = self.filter_reason(x, "novel")
                    if reason == "pass":
                        if self.match_tag_filter(x, tag_terms):
                            batch.append(x)
                        else:
                            reasons["tag"] += 1
                    elif reason in reasons:
                        reasons[reason] += 1
                items = unique_items(items + batch)
                self.set_debug_info(f"{method_name} 分页", resp, len(raw_batch), len(items), reasons)
                if len(items) >= count:
                    self.set_collect_end_reason("已找到请求数量")
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                self.set_collect_end_reason("Pixiv 没有下一页")
                break
        if len(items) < count and self.collect_end_reason_text() == "未知原因":
            self.set_collect_end_reason(f"达到最大搜索深度 {max_pages}")
        return items[:count]
