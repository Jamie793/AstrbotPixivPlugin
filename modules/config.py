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


class ConfigMixin:
    def cfg(self):
        proxy = str(self.config.get("proxy") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
        quality = str(self.config.get("image_quality", "large") or "large").lower()
        if quality not in {"medium", "large", "original"}:
            quality = "large"
        download_dir = str(self.config.get("download_dir", "data/downloads") or "data/downloads")
        dl_path = Path(download_dir)
        if not dl_path.is_absolute():
            dl_path = DATA_DIR / dl_path
        return {
            "refresh_token": str(self.config.get("refresh_token") or "").strip(),
            "refresh_token_interval_hours": max(0, int(self.config.get("refresh_token_interval_hours", 72) or 72)),
            "proxy": proxy,
            "use_image_proxy_without_proxy": bool(self.config.get("use_image_proxy_without_proxy", True)),
            "image_proxy_host": str(self.config.get("image_proxy_host", "https://i.pixiv.re") or "https://i.pixiv.re").rstrip("/"),
            "default_count": max(1, int(self.config.get("default_count", 20) or 20)),
            "max_count": max(1, int(self.config.get("max_count", 100) or 100)),
            "image_quality": quality,
            "image_preview_quality": quality,
            "allow_r18_group": bool(self.config.get("allow_r18_group", False)),
            "allow_r18_private": bool(self.config.get("allow_r18_private", False)),
            "allow_ai": bool(self.config.get("allow_ai", True)),
            "admin_discovery": bool((self.config.get("admin_permissions") or {}).get("admin_discovery", self.config.get("admin_discovery", True))),
            "admin_bookmark": bool((self.config.get("admin_permissions") or {}).get("admin_bookmark", self.config.get("admin_bookmark", True))),
            "admin_bookmarks": bool((self.config.get("admin_permissions") or {}).get("admin_bookmarks", self.config.get("admin_bookmarks", True))),
            "admin_follow": bool((self.config.get("admin_permissions") or {}).get("admin_follow", self.config.get("admin_follow", True))),
            "admin_following": bool((self.config.get("admin_permissions") or {}).get("admin_following", self.config.get("admin_following", True))),
            "admin_follow_latest": bool((self.config.get("admin_permissions") or {}).get("admin_follow_latest", self.config.get("admin_follow_latest", True))),
            "admin_recommended_users": bool((self.config.get("admin_permissions") or {}).get("admin_recommended_users", self.config.get("admin_recommended_users", True))),
            "admin_novel_recommended": bool((self.config.get("admin_permissions") or {}).get("admin_novel_recommended", self.config.get("admin_novel_recommended", True))),
            "admin_clean": bool((self.config.get("admin_permissions") or {}).get("admin_clean", self.config.get("admin_clean", True))),
            "admin_r18_manage": bool((self.config.get("admin_permissions") or {}).get("admin_r18_manage", self.config.get("admin_r18_manage", True))),
            "min_bookmarks": max(-1, int(self.config.get("min_bookmarks", -1) if self.config.get("min_bookmarks", -1) is not None else -1)),
            "min_views": max(-1, int(self.config.get("min_views", -1) if self.config.get("min_views", -1) is not None else -1)),
            "min_likes": max(-1, int(self.config.get("min_likes", -1) if self.config.get("min_likes", -1) is not None else -1)),
            "search_max_depth": max(1, int(self.config.get("search_max_depth", 10) if self.config.get("search_max_depth", 10) is not None else 10)),
            "concurrent_downloads": max(1, min(int(self.config.get("concurrent_downloads", 3) or 3), 8)),
            "request_timeout": max(10, int(self.config.get("request_timeout", 60) or 60)),
            "download_dir": dl_path,
            "include_info_txt": bool(self.config.get("include_info_txt", True)),
            "clean_after_send": bool(self.config.get("clean_after_send", False)),
            "auto_clean_enabled": bool(self.config.get("auto_clean_enabled", True)),
            "auto_clean_hour": max(0, min(int(self.config.get("auto_clean_hour", 4) if self.config.get("auto_clean_hour", 4) is not None else 4), 23)),
            "auto_clean_minute": max(0, min(int(self.config.get("auto_clean_minute", 0) if self.config.get("auto_clean_minute", 0) is not None else 0), 59)),
            "max_zip_mb": max(1, int(self.config.get("max_zip_mb", 200) or 200)),
            "send_mode": str(self.config.get("send_mode", "zip") or "zip"),
            "forward_mode": str(self.config.get("forward_mode", "info_and_images") or "info_and_images"),
            "forward_threshold": max(1, min(int(self.config.get("forward_threshold", 5) or 5), 20)),
            "include_work_info": bool(self.config.get("include_work_info", True)),
            "include_tags": bool(self.config.get("include_tags", True)),
            "max_tags_display": max(0, int(self.config.get("max_tags_display", 20) or 20)),
            "include_caption": bool(self.config.get("include_caption", True)),
            "novel_enabled": bool(self.config.get("novel_enabled", True)),
            "novel_send_mode": str(self.config.get("novel_send_mode", "zip") or "zip"),
            "novel_text_max_chars": max(500, int(self.config.get("novel_text_max_chars", 3000) or 3000)),
            "novel_preview_max_chars": max(50, int(self.config.get("novel_preview_max_chars", 500) or 500)),
            "novel_preview_total_chars": max(200, int(self.config.get("novel_preview_total_chars", 1800) or 1800)),
            "novel_split_chars": max(500, int(self.config.get("novel_split_chars", 1500) or 1500)),
            "include_novel_cover": bool(self.config.get("include_novel_cover", True)),
            "include_novel_info": bool(self.config.get("include_novel_info", True)),
            "tag_search_target": str(self.config.get("tag_search_target", "partial_match_for_tags") or "partial_match_for_tags"),
            "keyword_search_target": str(self.config.get("keyword_search_target", "partial_match_for_tags") or "partial_match_for_tags"),
            "and_filter_strict": bool(self.config.get("and_filter_strict", True)),
            "or_merge_dedupe": bool(self.config.get("or_merge_dedupe", True)),
        }
