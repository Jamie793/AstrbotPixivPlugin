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


class SenderService(BaseService):
    async def send_zip(self, event: AstrMessageEvent, zip_path: Path, suppress_ready: bool = False):
        c = self.cfg()
        size = zip_path.stat().st_size
        size_text = self.format_size(size)
        if size > c["max_zip_mb"] * 1024 * 1024:
            yield event.plain_result(f"ZIP 大小 {size_text}，超过限制 {c['max_zip_mb']}MB，已取消发送。")
            return
        password = self.pop_zip_password()
        if not suppress_ready:
            if password:
                yield event.plain_result(f"ZIP 已生成：{zip_path.name}，大小 {size_text}，已加密。解压密码：【{password}】。正在发送文件……")
            else:
                yield event.plain_result(f"ZIP 已生成：{zip_path.name}，大小 {size_text}，正在发送文件……")
        elif password:
            yield event.plain_result(f"缓存 ZIP 已加密。解压密码：【{password}】")
        try:
            # 优先使用本地文件路径发送，部分适配器对 base64 文件消息支持不稳定。
            yield event.chain_result([File(name=zip_path.name, file=str(zip_path))])
            yield event.plain_result("ZIP 文件发送请求已提交。若聊天窗口未显示文件，请检查当前适配器是否支持本地路径文件消息。")
            return
        except Exception as e1:
            logger.warning(f"pixivc zip send by path failed: {e1}", exc_info=True)
            try:
                data = base64.b64encode(zip_path.read_bytes()).decode()
                yield event.chain_result([File(name=zip_path.name, file="base64://" + data)])
                yield event.plain_result("ZIP 文件发送请求已提交（base64 兜底）。若聊天窗口未显示文件，请检查当前适配器文件消息支持。")
                return
            except Exception as e2:
                yield event.plain_result(f"ZIP 文件发送失败：本地路径发送失败：{e1}；base64 发送失败：{e2}")

    async def send_images(self, event, saved):
        c = self.cfg()
        for p, item, idx, total in saved:
            comps = [Image.fromFileSystem(str(p))]
            if c["include_work_info"]:
                comps.append(Plain(build_illust_info(item, idx, total, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"])))
            yield event.chain_result(comps)
            await asyncio.sleep(0.2)

    async def send_forward(self, event, saved, novel_infos=None):
        c = self.cfg()
        batch_size = 20
        if novel_infos is not None:
            all_infos = list(novel_infos or [])
            total = len(all_infos)
            if not all_infos:
                return
            for start in range(0, total, batch_size):
                part = all_infos[start:start + batch_size]
                nodes = [Node(name="PixivcNovel", uin="0", content=[Plain(info)]) for info in part]
                if total > batch_size:
                    yield event.plain_result(f"正在发送小说合并转发预览：{start + 1}-{start + len(part)}/{total}")
                yield event.chain_result([Nodes(nodes)])
                await asyncio.sleep(0.2)
            return

        all_saved = list(saved or [])
        total = len(all_saved)
        if not all_saved:
            return
        for start in range(0, total, batch_size):
            part = all_saved[start:start + batch_size]
            nodes = []
            for p, item, idx, total_pages in part:
                content = [Image.fromFileSystem(str(p))]
                if c["forward_mode"] != "only_images":
                    content.append(Plain(build_illust_info(item, idx, total_pages, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"])))
                nodes.append(Node(name="Pixivc", uin="0", content=content))
            if total > batch_size:
                yield event.plain_result(f"正在发送图片合并转发预览：{start + 1}-{start + len(part)}/{total}")
            yield event.chain_result([Nodes(nodes)])
            await asyncio.sleep(0.2)

    def _plain_item(self, item):
        if isinstance(item, dict):
            return item
        try:
            if hasattr(item, "__dict__"):
                return item.__dict__
        except Exception:
            pass
        return item

    async def dispatch_illust_result(self, event, base, zip_path, saved):
        c = self.cfg()
        # 图片搜索默认只发送合并转发预览，不自动生成/发送 ZIP。
        preview_saved = saved
        async for r in self.send_forward(event, preview_saved):
            yield r
        if c["clean_after_send"]:
            shutil.rmtree(base, ignore_errors=True)

    async def dispatch_novel_result(self, event, base, zip_path, files, infos):
        c = self.cfg()
        mode = c["novel_send_mode"]
        if mode == "zip":
            async for r in self.send_zip(event, zip_path):
                yield r
        elif mode == "txt_file":
            for p, item, text in files:
                if p.suffix.lower() == ".txt":
                    data = base64.b64encode(p.read_bytes()).decode()
                    yield event.chain_result([File(name=p.name, file="base64://" + data)])
        elif mode == "text":
            for p, item, text in files:
                if p.suffix.lower() == ".txt":
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    yield event.plain_result(content[:c["novel_text_max_chars"]])
        elif mode == "forward":
            async for r in self.send_forward(event, [], novel_infos=infos if c["include_novel_info"] else ["小说信息已按配置隐藏"]):
                yield r
        if c["clean_after_send"]:
            shutil.rmtree(base, ignore_errors=True)
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def build_novel_preview_infos(self, items):
        c = self.cfg()
        infos = []
        total = max(1, len(items))
        used_preview_chars = 0
        total_budget = c["novel_preview_total_chars"]
        skip_msg = "\n\n正文预览：为避免内容过长，后续作品不展示正文预览。"
        for item in items:
            info = build_novel_info(item, c["include_tags"], c["max_tags_display"], c["include_caption"])
            nid = item_id(item)
            if used_preview_chars >= total_budget:
                info += skip_msg
                infos.append(info)
                continue
            text = ""
            if nid:
                try:
                    text = await self.fetch_novel_text(nid)
                except Exception as e:
                    logger.warning(f"pixivc novel preview text failed {nid}: {e}")
                    text = ""
            if text:
                if total == 1:
                    dynamic_len = len(text)
                else:
                    dynamic_len = max(1, len(text) // (total + 1))
                remaining_budget = max(0, total_budget - used_preview_chars)
                preview_len = min(dynamic_len, c["novel_preview_max_chars"], remaining_budget)
                if preview_len > 0:
                    preview = text[:preview_len]
                    used_preview_chars += len(preview)
                    more = "\n……" if len(text) > preview_len else ""
                    info += f"\n\n正文预览：\n{preview}{more}"
                else:
                    info += skip_msg
            else:
                info += "\n\n正文预览：获取失败或为空"
            infos.append(info)
        return infos
