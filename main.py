import asyncio
import base64
import html
import json
import os
import re
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import aiohttp
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import At, File, Image, Node, Nodes, Plain
from pixivpy3 import AppPixivAPI, ByPassSniApi

try:
    from .modules.help import build_help_text as build_pixivc_help_text
    from .modules.oauth import generate_login_url, exchange_token, token_parts
except ImportError:
    from modules.help import build_help_text as build_pixivc_help_text
    from modules.oauth import generate_login_url, exchange_token, token_parts

PLUGIN_DIR = Path(__file__).parent
DATA_DIR = PLUGIN_DIR / "data"
DEFAULT_DOWNLOAD_DIR = DATA_DIR / "downloads"
R18_WHITELIST_FILE = DATA_DIR / "r18_whitelist.json"
LAST_ZIP_FILE = DATA_DIR / "last_zip.json"
LAST_ITEMS_FILE = DATA_DIR / "last_items.json"
OAUTH_STATE_FILE = DATA_DIR / "oauth_state.json"
OWNER_QQ = "10627452"
HELP_TEXT = """Pixivc 爬虫帮助：

图片命令：
1. /pixivc_key xxx [数量]
2. /pixivc_tag xxx [数量]
3. /pixivc_key_and xxx,xxx2 [数量]
4. /pixivc_key_or xxx,xxx2 [数量]
5. /pixivc_tag_and xxx,xxx2 [数量]
6. /pixivc_tag_or xxx,xxx2 [数量]
7. /pixivc_rank daily [数量]
8. /pixivc_user 123456 [数量]
9. /pixivc_discovery [Admin] [数量]

小说命令：
10. /pixivc_novel_key xxx [数量]
11. /pixivc_novel_tag xxx [数量]
12. /pixivc_novel_key_and xxx,xxx2 [数量]
13. /pixivc_novel_key_or xxx,xxx2 [数量]
14. /pixivc_novel_tag_and xxx,xxx2 [数量]
15. /pixivc_novel_tag_or xxx,xxx2 [数量]
16. /pixivc_novel_rank daily [数量]
17. /pixivc_novel_user 123456 [数量]
18. /pixivc_novel_id 123456789

管理命令：
19. /pixivc_help
20. /pixivc_status
21. /pixivc_clean [Admin]
22. /pixivc_get_zip
23. /pixivc_r18_add [Admin] QQ 或 @某人
24. /pixivc_r18_del [Admin] QQ 或 @某人
25. /pixivc_r18_list [Admin]
26. /pixivc_auto xxx
27. /pixivc_illust_id 作品ID
28. /pixivc_bookmark_add [Admin] 作品ID
29. /pixivc_bookmark_del [Admin] 作品ID
30. /pixivc_bookmarks [Admin] [数量]
31. /pixivc_trending_tags
32. /pixivc_related 作品ID [数量]
33. /pixivc_follow_add [Admin] 用户ID
34. /pixivc_follow_del [Admin] 用户ID
35. /pixivc_following [Admin] [数量]
36. /pixivc_follow_latest [Admin] [数量]
37. /pixivc_new [数量]
38. /pixivc_recommended_users [Admin] [数量]
39. /pixivc_user_search 关键词 [数量]

说明：
- 默认数量为20；最大数量由 max_count 配置决定。
- 可用 page 参数指定从第几页开始，例如：/pixivc_tag 原神 20 page=3，或 /pixivc_tag 原神 20 3。
- 预览图片质量 medium/large/original 在插件设置 image_quality 中配置；ZIP 固定 original。
- 图片搜索默认只发送合并转发预览，不自动发送 ZIP。
- 如需最近一次搜索的 original ZIP，请发送 /pixivc_get_zip。
- 发送模式 send_mode/novel_send_mode 在插件设置中配置。
- R18 需要对应场景开关开启，并且发送者 QQ 在 R18 白名单内。
- /pixivc_auto xxx 可调用 Pixiv API 获取关键词/标签自动补全。
"""


def read_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_filename(name: str, max_len: int = 80) -> str:
    name = html.unescape(str(name or ""))
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", name)
    name = name.strip(" ._") or "untitled"
    return name[:max_len]


def getv(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def to_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def split_terms(text: str):
    return [x.strip() for x in re.split(r"[,，]", text or "") if x.strip()]


def parse_count_arg(text: str, default_count: int, max_count: int):
    text = (text or "").strip()
    if not text:
        return "", max(1, min(default_count, max_count))
    parts = text.rsplit(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0].strip(), max(1, min(int(parts[1]), max_count))
    if text.isdigit():
        return "", max(1, min(int(text), max_count))
    return text, max(1, min(default_count, max_count))


def full_command_args(event: AstrMessageEvent, command_name: str, injected: str = "") -> str:
    """优先从完整 message_str 提取命令后的全部参数，避免 AstrBot 参数注入只取首段。"""
    text = (getattr(event, "message_str", "") or "").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    if text == command_name:
        return ""
    prefix = command_name + " "
    if text.startswith(prefix):
        return text[len(prefix):].strip()
    return (injected or "").strip()


def tags_text(item) -> list[str]:
    tags = []
    for tag in getv(item, "tags", []) or []:
        name = getv(tag, "name", "")
        trans = getv(tag, "translated_name", "")
        if name:
            tags.append(str(name))
        if trans:
            tags.append(str(trans))
    return tags


def searchable_text(item) -> str:
    parts = [getv(item, "title", ""), getv(item, "caption", ""), getv(item, "user", {}) and getv(getv(item, "user", {}), "name", "")]
    parts.extend(tags_text(item))
    return " ".join(str(x or "") for x in parts).lower()


def is_r18(item) -> bool:
    return to_int(getv(item, "x_restrict", 0), 0) != 0


def is_ai(item) -> bool:
    return to_int(getv(item, "illust_ai_type", getv(item, "ai_type", 0)), 0) == 2


def stat_value(item, *keys):
    for k in keys:
        v = getv(item, k, None)
        if v is not None:
            return to_int(v, 0)
    return 0


def item_id(item):
    return str(getv(item, "id", ""))


def unique_items(items: Iterable[Any]):
    seen = set()
    out = []
    for item in items:
        iid = item_id(item)
        if iid and iid not in seen:
            seen.add(iid)
            out.append(item)
    return out


def extract_items(resp, kind="illust"):
    if not resp:
        return []
    keys = ["illusts", "ranking_illusts", "novels", "ranking_novels"] if kind == "illust" else ["novels", "ranking_novels"]
    for key in keys:
        value = getv(resp, key, None)
        if value:
            return list(value)
    return []


def pick_image_url(item, quality: str):
    urls = []
    meta_pages = getv(item, "meta_pages", None) or []
    if meta_pages:
        for page in meta_pages:
            urls.append(getv(page, "image_urls", {}) or {})
    else:
        image_urls = dict(getv(item, "image_urls", {}) or {})
        meta_single = getv(item, "meta_single_page", {}) or {}
        original = getv(meta_single, "original_image_url", None)
        if original:
            image_urls["original"] = original
        urls.append(image_urls)

    order = {
        "original": ["original", "large", "medium", "square_medium"],
        "large": ["large", "original", "medium", "square_medium"],
        "medium": ["medium", "large", "original", "square_medium"],
    }.get(quality, ["large", "original", "medium", "square_medium"])
    result = []
    for u in urls:
        for key in order:
            if isinstance(u, dict) and u.get(key):
                result.append(u[key])
                break
    return result


def novel_cover_url(item):
    image_urls = getv(item, "image_urls", {}) or {}
    if isinstance(image_urls, dict):
        return image_urls.get("large") or image_urls.get("medium") or image_urls.get("square_medium") or ""
    return ""


def fmt_time(value):
    return str(value or "未知")


def user_info(item):
    user = getv(item, "user", {}) or {}
    return str(getv(user, "name", "未知")), str(getv(user, "id", "未知"))


def build_illust_info(item, page=None, page_total=None, quality="large", include_tags=True, max_tags=20, include_caption=True):
    author, author_id = user_info(item)
    iid = item_id(item)
    tags = tags_text(item)
    lines = [
        f"标题：{getv(item, 'title', '未知')}",
        f"作者：{author}",
        f"作者ID：{author_id}",
        f"作品ID：{iid}",
        f"发布时间：{fmt_time(getv(item, 'create_date', ''))}",
        f"类型：{getv(item, 'type', 'illust')}",
        f"图片质量：{quality}",
        f"链接：https://www.pixiv.net/artworks/{iid}",
    ]
    if include_tags and tags:
        lines.append("标签：" + "、".join(tags[:max_tags]))
    if include_caption and getv(item, "caption", ""):
        cap = re.sub(r"<[^>]+>", "", str(getv(item, "caption", "")))
        lines.append("简介：" + html.unescape(cap)[:500])
    return "\n".join(lines)


def build_novel_info(item, include_tags=True, max_tags=20, include_caption=True):
    author, author_id = user_info(item)
    nid = item_id(item)
    series = getv(item, "series", {}) or {}
    tags = tags_text(item)
    lines = [
        f"小说标题：{getv(item, 'title', '未知')}",
        f"作者：{author}",
        f"作者ID：{author_id}",
        f"小说ID：{nid}",
        f"发布时间：{fmt_time(getv(item, 'create_date', ''))}",
        f"更新时间：{fmt_time(getv(item, 'update_date', ''))}",
        f"字数：{stat_value(item, 'text_length')}",
        f"系列ID：{getv(series, 'id', '无')}",
        f"系列标题：{getv(series, 'title', '无')}",
        f"第几话：{getv(series, 'order', '未知')}",
        f"浏览：{stat_value(item, 'total_view', 'total_views')}",
        f"收藏：{stat_value(item, 'total_bookmarks')}",
        f"评论：{stat_value(item, 'total_comments', 'comment_count', 'commentCount')}",
        f"R18：{'是' if is_r18(item) else '否'}",
        f"AI：{'是' if is_ai(item) else '否'}",
        f"链接：https://www.pixiv.net/novel/show.php?id={nid}",
    ]
    if include_tags and tags:
        lines.append("标签：" + "、".join(tags[:max_tags]))
    if include_caption and getv(item, "caption", ""):
        cap = re.sub(r"<[^>]+>", "", str(getv(item, "caption", "")))
        lines.append("简介：" + html.unescape(cap)[:1000])
    return "\n".join(lines)

@register(
    "astrbot_plugin_pixivc_crawler",
    "local",
    "Pixiv 非 Scrapy 批量爬取插件：图片/小说/AND/OR/ZIP/转发，最大20",
    "1.3.0",
)
class PixivcCrawlerPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._api = None
        self._auth_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self._current_allow_r18 = None
        self._current_start_page_override = None
        self._clean_task = None

    async def initialize(self):
        c = self.cfg()
        if c["auto_clean_enabled"] and (self._clean_task is None or self._clean_task.done()):
            self._clean_task = asyncio.create_task(self.auto_clean_loop())
            logger.info(f"Pixivc 每日自动清理已启用：{c['auto_clean_hour']:02d}:{c['auto_clean_minute']:02d}")

    async def terminate(self):
        if self._clean_task and not self._clean_task.done():
            self._clean_task.cancel()
            logger.info("Pixivc 每日自动清理任务已停止")

    def next_clean_time(self):
        c = self.cfg()
        now = datetime.now()
        nxt = now.replace(hour=c["auto_clean_hour"], minute=c["auto_clean_minute"], second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt

    async def auto_clean_loop(self):
        while True:
            try:
                nxt = self.next_clean_time()
                wait = max(1, (nxt - datetime.now()).total_seconds())
                await asyncio.sleep(wait)
                await self.clean_download_cache(reason="daily_auto")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Pixivc 每日自动清理失败：{e}", exc_info=True)
                await asyncio.sleep(60)

    async def clean_download_cache(self, reason="manual"):
        c = self.cfg()
        d = c["download_dir"]
        if self._task_lock.locked():
            logger.info("Pixivc 清理跳过：当前有爬取任务正在执行")
            return False
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        try:
            LAST_ZIP_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        logger.info(f"Pixivc 下载缓存已清理，reason={reason}")
        return True

    def cfg(self):
        proxy = str(self.config.get("proxy") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
        quality = str(self.config.get("image_quality", "large") or "large").lower()
        if quality not in {"medium", "large", "original"}:
            quality = "large"
        download_dir = str(self.config.get("download_dir", "data/downloads") or "data/downloads")
        dl_path = Path(download_dir)
        if not dl_path.is_absolute():
            dl_path = PLUGIN_DIR / dl_path
        return {
            "refresh_token": str(self.config.get("refresh_token") or "").strip(),
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
            "search_pages": max(-1, int(self.config.get("search_pages", -1) if self.config.get("search_pages", -1) is not None else -1)),
            "search_start_page": max(1, int(self.config.get("search_start_page", 1) if self.config.get("search_start_page", 1) is not None else 1)),
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
            "novel_split_chars": max(500, int(self.config.get("novel_split_chars", 1500) or 1500)),
            "include_novel_cover": bool(self.config.get("include_novel_cover", True)),
            "include_novel_info": bool(self.config.get("include_novel_info", True)),
            "tag_search_target": str(self.config.get("tag_search_target", "partial_match_for_tags") or "partial_match_for_tags"),
            "keyword_search_target": str(self.config.get("keyword_search_target", "partial_match_for_tags") or "partial_match_for_tags"),
            "and_filter_strict": bool(self.config.get("and_filter_strict", True)),
            "or_merge_dedupe": bool(self.config.get("or_merge_dedupe", True)),
        }

    def create_api(self, proxy: str):
        if proxy:
            return AppPixivAPI(proxies={"http": proxy, "https": proxy})
        try:
            return ByPassSniApi()
        except Exception:
            return AppPixivAPI()

    async def api(self):
        c = self.cfg()
        if not c["refresh_token"]:
            raise RuntimeError("未配置 Pixiv refresh_token，请在本插件设置中填写。")
        async with self._auth_lock:
            if self._api is None:
                self._api = self.create_api(c["proxy"])
                await asyncio.to_thread(self._api.auth, refresh_token=c["refresh_token"])
            return self._api

    def _looks_auth_failed(self, exc=None, resp=None) -> bool:
        if resp is not None:
            status = getattr(resp, "status_code", None)
            if status in (401, 403):
                return True
            try:
                err = resp.json()
            except Exception:
                err = None
            text = str(err if err is not None else getattr(resp, "text", ""))
        else:
            text = str(exc or "")
        lower = text.lower()
        return any(k in lower for k in ["invalid_grant", "invalid_request", "invalid token", "access token", "unauthorized", "oauth", "token expired", "expired token"])

    async def refresh_api_silent(self):
        c = self.cfg()
        if not c["refresh_token"]:
            raise RuntimeError("未配置 Pixiv refresh_token，请在本插件设置中填写。")
        async with self._auth_lock:
            logger.info("Pixivc access token 可能失效，正在后台静默刷新。")
            self._api = self.create_api(c["proxy"])
            await asyncio.to_thread(self._api.auth, refresh_token=c["refresh_token"])
            return self._api

    async def api_call(self, method_name: str, *args, **kwargs):
        api = await self.api()
        method = getattr(api, method_name)
        try:
            resp = await asyncio.to_thread(method, *args, **kwargs)
            if self._looks_auth_failed(resp=resp):
                api = await self.refresh_api_silent()
                resp = await asyncio.to_thread(getattr(api, method_name), *args, **kwargs)
            return resp
        except Exception as e:
            if self._looks_auth_failed(exc=e):
                api = await self.refresh_api_silent()
                return await asyncio.to_thread(getattr(api, method_name), *args, **kwargs)
            raise

    async def api_requests_call(self, method: str, url: str, **kwargs):
        api = await self.api()
        try:
            resp = await asyncio.to_thread(api.requests_call, method, url, **kwargs)
            if self._looks_auth_failed(resp=resp):
                api = await self.refresh_api_silent()
                resp = await asyncio.to_thread(api.requests_call, method, url, **kwargs)
            return resp
        except Exception as e:
            if self._looks_auth_failed(exc=e):
                api = await self.refresh_api_silent()
                return await asyncio.to_thread(api.requests_call, method, url, **kwargs)
            raise

    async def api_no_auth_requests_call(self, method: str, url: str, **kwargs):
        api = await self.api()
        try:
            resp = await asyncio.to_thread(api.no_auth_requests_call, method, url, req_auth=True, **kwargs)
            if self._looks_auth_failed(resp=resp):
                api = await self.refresh_api_silent()
                resp = await asyncio.to_thread(api.no_auth_requests_call, method, url, req_auth=True, **kwargs)
            return resp
        except Exception as e:
            if self._looks_auth_failed(exc=e):
                api = await self.refresh_api_silent()
                return await asyncio.to_thread(api.no_auth_requests_call, method, url, req_auth=True, **kwargs)
            raise

    def parse_query_count(self, raw: str):
        c = self.cfg()
        text = (raw or "").strip()
        self._current_start_page_override = None
        page = None

        # 支持 page=3 / p=3 / start=3 / start_page=3 / 第3页 / p3
        patterns = [
            r"(?:^|\s)(?:page|p|start|start_page)\s*=\s*(\d+)(?=\s|$)",
            r"(?:^|\s)第\s*(\d+)\s*页(?=\s|$)",
            r"(?:^|\s)p(\d+)(?=\s|$)",
        ]
        for pat in patterns:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                page = max(1, int(m.group(1)))
                text = (text[:m.start()] + " " + text[m.end():]).strip()
                break

        # 支持末尾两个数字：关键词 数量 起始页，例如 /pixivc_tag 原神 20 3
        parts = text.rsplit(maxsplit=2)
        if page is None and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            text = (parts[0] + " " + parts[1]).strip()
            page = max(1, int(parts[2]))

        self._current_start_page_override = page
        return parse_count_arg(text, c["default_count"], c["max_count"])

    def effective_start_page(self):
        if self._current_start_page_override is not None:
            return max(1, int(self._current_start_page_override))
        return self.cfg()["search_start_page"]

    def sender_id(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id() or "").strip()
        except Exception:
            pass
        try:
            return str(getattr(getattr(event, "message_obj", None), "sender_id", "") or "").strip()
        except Exception:
            return ""

    def is_owner(self, event: AstrMessageEvent) -> bool:
        return self.sender_id(event) == OWNER_QQ

    def load_r18_whitelist(self):
        data = read_json(R18_WHITELIST_FILE, {"qq_list": []})
        raw = data.get("qq_list", []) if isinstance(data, dict) else []
        clean = []
        for x in raw:
            q = str(x).strip()
            if re.fullmatch(r"\d{5,12}", q) and q not in clean:
                clean.append(q)
        return clean

    def save_r18_whitelist(self, qq_list):
        clean = []
        for x in qq_list:
            q = str(x).strip()
            if re.fullmatch(r"\d{5,12}", q) and q not in clean:
                clean.append(q)
        write_json(R18_WHITELIST_FILE, {"qq_list": clean})
        return clean

    def first_at_qq(self, event: AstrMessageEvent) -> str:
        try:
            for comp in getattr(event.message_obj, "message", []) or []:
                if isinstance(comp, At) and str(comp.qq).lower() != "all":
                    q = str(comp.qq).strip()
                    if re.fullmatch(r"\d{5,12}", q):
                        return q
        except Exception:
            return ""
        return ""

    def extract_qq_arg(self, event: AstrMessageEvent, command_name: str, args: str = "") -> str:
        at = self.first_at_qq(event)
        if at:
            return at
        text = full_command_args(event, command_name, args)
        m = re.search(r"\b(\d{5,12})\b", text or "")
        return m.group(1) if m else ""

    def is_group_event(self, event: AstrMessageEvent) -> bool:
        try:
            gid = event.get_group_id()
            return bool(gid)
        except Exception:
            return False

    def is_bot_admin(self, event: AstrMessageEvent) -> bool:
        if self.is_owner(event):
            return True
        try:
            fn = getattr(event, "is_admin", None)
            if callable(fn):
                return bool(fn())
        except Exception:
            return False
        return False

    def allow_r18_for_event(self, event: AstrMessageEvent) -> bool:
        c = self.cfg()
        switch_on = c["allow_r18_group"] if self.is_group_event(event) else c["allow_r18_private"]
        if not switch_on:
            return False
        if self.is_bot_admin(event):
            return True
        sender = self.sender_id(event)
        return bool(sender and sender in self.load_r18_whitelist())

    def pass_filter(self, item, kind="illust"):
        c = self.cfg()
        allow_r18 = self._current_allow_r18 if self._current_allow_r18 is not None else False
        if not allow_r18 and is_r18(item):
            return False
        if not c["allow_ai"] and is_ai(item):
            return False
        if c["min_bookmarks"] >= 0 and stat_value(item, "total_bookmarks") < c["min_bookmarks"]:
            return False
        if c["min_views"] >= 0 and stat_value(item, "total_view", "total_views") < c["min_views"]:
            return False
        if c["min_likes"] >= 0 and stat_value(item, "total_like", "total_likes", "like_count", "likeCount") < c["min_likes"]:
            return False
        return True

    def and_match(self, item, terms, mode="key"):
        if not terms:
            return True
        if mode == "tag":
            hay = " ".join(tags_text(item)).lower()
        else:
            hay = searchable_text(item)
        return all(t.lower() in hay for t in terms)

    async def collect_page_search(self, api, query, count, kind="illust", target="partial_match_for_tags"):
        c = self.cfg()
        items = []
        next_qs = None
        max_pages = 1000 if c["search_pages"] == -1 else max(1, c["search_pages"])
        start_page = self.effective_start_page()
        for page in range(max_pages + start_page - 1):
            if kind == "illust":
                if next_qs:
                    resp = await self.api_call("search_illust", **next_qs)
                else:
                    resp = await self.api_call("search_illust", query, search_target=target, sort="date_desc")
            else:
                if next_qs:
                    resp = await self.api_call("search_novel", **next_qs)
                else:
                    resp = await self.api_call("search_novel", query, search_target=target, sort="date_desc")
            current_page = page + 1
            if current_page >= start_page:
                batch = [x for x in extract_items(resp, kind) if self.pass_filter(x, kind)]
                items = unique_items(items + batch)
                if len(items) >= count:
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                break
        return items[:count]

    async def collect_and_or(self, terms, count, kind="illust", mode="key", logic="single"):
        api = await self.api()
        c = self.cfg()
        target = c["tag_search_target"] if mode == "tag" else c["keyword_search_target"]
        if target == "keyword":
            target = "partial_match_for_tags"
        if logic == "or":
            all_items = []
            for term in terms:
                all_items += await self.collect_page_search(api, term, count, kind, target)
            return unique_items(all_items)[:count]
        query = terms[0] if terms else ""
        items = await self.collect_page_search(api, query, count * 2 if logic == "and" else count, kind, target)
        if logic == "and" and c["and_filter_strict"]:
            items = [x for x in items if self.and_match(x, terms, mode)]
        return items[:count]

    async def collect_rank(self, rank_mode, count, kind="illust"):
        api = await self.api()
        mode_map = {"daily": "day", "day": "day", "weekly": "week", "week": "week", "monthly": "month", "month": "month", "rookie": "rookie"}
        rank_mode = mode_map.get(str(rank_mode or "daily").lower(), str(rank_mode or "day"))
        if kind == "illust":
            resp = await self.api_call("illust_ranking", mode=rank_mode)
        else:
            # pixivpy3 当前没有 novel_ranking，小说榜第一版降级为推荐小说。
            # 保留 /pixivc_novel_rank 命令入口，后续可替换为 Web API 榜单实现。
            resp = await self.api_call("novel_recommended")
        items = [x for x in extract_items(resp, kind) if self.pass_filter(x, kind)]
        return unique_items(items)[:count]

    async def collect_user(self, user_id, count, kind="illust"):
        if not str(user_id).isdigit():
            raise RuntimeError("用户ID必须是数字")
        api = await self.api()
        if kind == "illust":
            resp = await self.api_call("user_illusts", int(user_id), type="illust")
        else:
            resp = await self.api_call("user_novels", int(user_id))
        items = [x for x in extract_items(resp, kind) if self.pass_filter(x, kind)]
        return unique_items(items)[:count]

    async def collect_discovery(self, count):
        api = await self.api()
        resp = await self.api_call("illust_recommended", include_ranking_illusts=True)
        items = [x for x in extract_items(resp, "illust") if self.pass_filter(x, "illust")]
        return unique_items(items)[:count]

    def convert_image_proxy_url(self, url: str, proxy=None) -> str:
        c = self.cfg()
        if proxy or not c["use_image_proxy_without_proxy"]:
            return url
        host = c["image_proxy_host"].rstrip("/")
        if not host:
            return url
        # i.pixiv.re 用法：把 https://i.pximg.net/... 替换为 https://i.pixiv.re/...
        for src in ("https://i.pximg.net", "http://i.pximg.net"):
            if str(url).startswith(src):
                return host + str(url)[len(src):]
        return url

    async def download_url(self, session, url, path, proxy=None, timeout=60):
        url = self.convert_image_proxy_url(url, proxy)
        headers = {"Referer": "https://www.pixiv.net/", "User-Agent": "Mozilla/5.0"}
        async with session.get(url, headers=headers, proxy=proxy or None, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            path.write_bytes(await resp.read())

    async def prepare_illust_files(self, items, label="pixivs"):
        c = self.cfg()
        ts = time.strftime("%Y%m%d_%H%M%S")
        base = c["download_dir"] / f"{safe_filename(label, 40)}_{ts}"
        img_dir = base / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(c["concurrent_downloads"])
        session_timeout = aiohttp.ClientTimeout(total=c["request_timeout"] + 30)
        saved = []
        infos = []

        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            async def one(item):
                iid = item_id(item)
                title = safe_filename(getv(item, "title", "untitled"), 50)
                urls = pick_image_url(item, c["image_quality"])
                total = len(urls)
                out = []
                for idx, url in enumerate(urls, 1):
                    if len(saved) + len(out) >= c["max_count"]:
                        break
                    ext = Path(url.split("?")[0]).suffix or ".jpg"
                    p = img_dir / f"{iid}_p{idx}_{title}{ext}"
                    async with sem:
                        try:
                            await self.download_url(session, url, p, c["proxy"], c["request_timeout"])
                            out.append((p, item, idx, total))
                        except Exception as e:
                            logger.warning(f"pixivc image download failed {iid} p{idx}: {e}")
                return out

            results = await asyncio.gather(*(one(x) for x in items), return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    continue
                for row in res:
                    if len(saved) >= c["max_count"]:
                        break
                    saved.append(row)

        for p, item, idx, total in saved:
            infos.append(build_illust_info(item, idx, total, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"]))
        info_path = base / "info.txt"
        info_path.write_text("\n\n".join(infos), encoding="utf-8")
        zip_path = c["download_dir"] / f"{safe_filename(label, 40)}_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if c["include_info_txt"]:
                zf.write(info_path, "info.txt")
            for p, *_ in saved:
                zf.write(p, f"images/{p.name}")
        return base, zip_path, saved

    async def fetch_novel_text(self, novel_id):
        api = await self.api()
        try:
            resp = await self.api_call("novel_text", int(novel_id))
            text = getv(resp, "novel_text", "") or getv(resp, "text", "") or ""
            return str(text)
        except Exception as e:
            logger.warning(f"pixivc novel text failed {novel_id}: {e}")
            return ""

    async def prepare_original_zip_from_items(self, items, label="pixivc_original"):
        old_quality = self.config.get("image_quality")
        self.config["image_quality"] = "original"
        try:
            return await self.prepare_illust_files(items, label)
        finally:
            if old_quality is None:
                self.config.pop("image_quality", None)
            else:
                self.config["image_quality"] = old_quality

    async def prepare_novel_files(self, items, label="pixivc_novel"):
        c = self.cfg()
        ts = time.strftime("%Y%m%d_%H%M%S")
        base = c["download_dir"] / f"{safe_filename(label, 40)}_{ts}"
        novel_dir = base / "novels"
        cover_dir = base / "covers"
        novel_dir.mkdir(parents=True, exist_ok=True)
        cover_dir.mkdir(parents=True, exist_ok=True)
        session_timeout = aiohttp.ClientTimeout(total=c["request_timeout"] + 30)
        files = []
        infos = []
        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            for item in items:
                nid = item_id(item)
                title = safe_filename(getv(item, "title", "untitled"), 60)
                info = build_novel_info(item, c["include_tags"], c["max_tags_display"], c["include_caption"])
                infos.append(info)
                text = await self.fetch_novel_text(nid)
                txt_path = novel_dir / f"{nid}_{title}.txt"
                txt_path.write_text(info + "\n\n" + (text or "小说正文获取失败或为空"), encoding="utf-8")
                files.append((txt_path, item, text))
                if c["include_novel_cover"]:
                    url = novel_cover_url(item)
                    if url:
                        ext = Path(url.split("?")[0]).suffix or ".jpg"
                        cover_path = cover_dir / f"{nid}_cover{ext}"
                        try:
                            await self.download_url(session, url, cover_path, c["proxy"], c["request_timeout"])
                            files.append((cover_path, item, ""))
                        except Exception:
                            pass
        info_path = base / "info.txt"
        info_path.write_text("\n\n".join(infos), encoding="utf-8")
        zip_path = c["download_dir"] / f"{safe_filename(label, 40)}_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if c["include_info_txt"]:
                zf.write(info_path, "info.txt")
            for p, item, text in files:
                sub = "covers" if "cover" in p.name else "novels"
                zf.write(p, f"{sub}/{p.name}")
        return base, zip_path, files, infos

    async def send_zip(self, event: AstrMessageEvent, zip_path: Path):
        c = self.cfg()
        if zip_path.stat().st_size > c["max_zip_mb"] * 1024 * 1024:
            yield event.plain_result(f"ZIP 超过大小限制 {c['max_zip_mb']}MB，已取消发送。")
            return
        data = base64.b64encode(zip_path.read_bytes()).decode()
        yield event.chain_result([File(name=zip_path.name, file="base64://" + data)])

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
        if c["forward_mode"] == "none" and novel_infos is not None:
            return
        nodes = []
        if novel_infos is not None:
            for info in novel_infos:
                nodes.append(Node(name="PixivcNovel", uin="0", content=[Plain(info)]))
        else:
            for p, item, idx, total in saved:
                content = [Image.fromFileSystem(str(p))]
                if c["forward_mode"] != "only_images":
                    content.append(Plain(build_illust_info(item, idx, total, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"])))
                nodes.append(Node(name="Pixivc", uin="0", content=content))
        if nodes:
            yield event.chain_result([Nodes(nodes)])

    def _plain_item(self, item):
        if isinstance(item, dict):
            return item
        try:
            if hasattr(item, "__dict__"):
                return item.__dict__
        except Exception:
            pass
        return item

    def save_last_items(self, event: AstrMessageEvent, items, label: str, kind: str = "illust"):
        data = {
            "kind": str(kind),
            "label": str(label),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sender_id": self.sender_id(event),
            "items": [self._plain_item(x) for x in items],
        }
        try:
            gid = event.get_group_id()
        except Exception:
            gid = ""
        data["group_id"] = str(gid or "")
        write_json(LAST_ITEMS_FILE, data)
        try:
            LAST_ZIP_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    def load_last_items(self):
        data = read_json(LAST_ITEMS_FILE, {})
        if not isinstance(data, dict):
            return {}
        items = data.get("items") or []
        if not isinstance(items, list) or not items:
            return {}
        return data

    def save_last_zip(self, event: AstrMessageEvent, zip_path: Path, label: str, count: int, kind: str = "illust"):
        data = {
            "kind": str(kind),
            "path": str(zip_path),
            "name": zip_path.name,
            "label": str(label),
            "count": int(count),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sender_id": self.sender_id(event),
        }
        try:
            gid = event.get_group_id()
        except Exception:
            gid = ""
        data["group_id"] = str(gid or "")
        write_json(LAST_ZIP_FILE, data)

    def load_last_zip(self):
        data = read_json(LAST_ZIP_FILE, {})
        if not isinstance(data, dict):
            return {}
        path = Path(str(data.get("path") or ""))
        if not path.exists() or not path.is_file():
            return {}
        data["path"] = str(path)
        return data

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

    async def run_illust_job(self, event, label, collector):
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
                            yield event.plain_result(f"开始爬取 Pixiv：{label}。")
                        else:
                            logger.info("Pixivc 已静默刷新 access token，正在自动重试本次图片命令。")
                        items = await collector()
                        if not items:
                            yield event.plain_result("没有找到符合条件的作品，可能是过滤条件过严或关键词无结果。")
                            return
                        self.save_last_items(event, items, label, "illust")
                        base, zip_path, saved = await self.prepare_illust_files(items, "pixivc_preview_" + label)
                        if not saved:
                            yield event.plain_result("找到作品但图片下载失败，请检查代理或 Pixiv 访问。")
                            return
                        try:
                            zip_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        yield event.plain_result(f"下载完成：{len(saved)} 张，正在发送图片合并转发预览。需要 original ZIP 请发送 /pixivc_get_zip")
                        async for r in self.dispatch_illust_result(event, base, zip_path, saved):
                            yield r
                        return
                    except Exception as e:
                        if attempt == 0 and self._looks_auth_failed(exc=e):
                            await self.refresh_api_silent()
                            continue
                        logger.error(f"pixivc illust job failed: {e}", exc_info=True)
                        yield event.plain_result(f"爬取失败：{e}")
                        return
            finally:
                self._current_allow_r18 = None

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
                            yield event.plain_result("没有找到符合条件的小说，可能是过滤条件过严或关键词无结果。")
                            return
                        self.save_last_items(event, items, label, "novel")
                        infos = [build_novel_info(x, c["include_tags"], c["max_tags_display"], c["include_caption"]) for x in items]
                        yield event.plain_result(f"小说处理完成：{len(items)} 篇，正在发送合并转发预览。需要小说 ZIP 请发送 /pixivc_get_zip")
                        async for r in self.send_forward(event, [], novel_infos=infos if c["include_novel_info"] else ["小说信息已按配置隐藏"]):
                            yield r
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

    def admin_mark(self, key: str) -> str:
        return " [Admin]" if self.cfg().get(key, True) else ""

    def build_help_text(self) -> str:
        return build_pixivc_help_text(self.admin_mark)


    @filter.command("pixivc_get_token", alias={"获取P站Token"})
    async def pixivc_get_token(self, event: AstrMessageEvent):
        yield event.plain_result("我正在生成 Pixiv 官方 OAuth 登录链接。")
        try:
            url = await asyncio.to_thread(generate_login_url, OAUTH_STATE_FILE)
            yield event.plain_result(url)
        except Exception as e:
            logger.error(f"pixiv oauth generate login failed: {e}", exc_info=True)
            yield event.plain_result(f"生成 Pixiv 登录链接失败：{e}")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=2)
    async def pixiv_oauth_callback_listener(self, event: AstrMessageEvent):
        text = getattr(event, "message_str", "") or ""
        if "code=" not in text:
            return
        yield event.plain_result("正在处理 Pixiv OAuth 回调并获取 token。")
        obj = await asyncio.to_thread(exchange_token, text, OAUTH_STATE_FILE)
        raw = json.dumps(obj, ensure_ascii=False, indent=2)
        access_token, refresh_token = token_parts(obj)
        yield event.plain_result(raw)
        if access_token:
            yield event.plain_result("accesstoken")
            yield event.plain_result(access_token)
        if refresh_token:
            yield event.plain_result("refreshtoken")
            yield event.plain_result(refresh_token)
        event.stop_event()

    @filter.command("pixivc_help", alias={"pixivs帮助"})
    async def pixivc_help(self, event: AstrMessageEvent):
        yield event.plain_result(self.build_help_text())

    def extract_first_illust(self, resp):
        if isinstance(resp, dict):
            item = resp.get("illust") or resp.get("illustration")
            if item:
                return item
        return None

    def extract_users(self, resp):
        if isinstance(resp, dict):
            users = resp.get("users") or resp.get("user_previews") or []
            out = []
            for x in users:
                if isinstance(x, dict) and "user" in x:
                    out.append(x.get("user"))
                else:
                    out.append(x)
            return [x for x in out if x]
        return []

    def format_users(self, users, limit=20):
        lines = []
        for i, u in enumerate(users[:limit], 1):
            uid = getv(u, "id", "未知")
            name = getv(u, "name", "未知")
            account = getv(u, "account", "")
            extra = f" @{account}" if account else ""
            lines.append(f"{i}. {name}{extra} ID：{uid}")
        return "Pixivc 用户列表：\n" + "\n".join(lines) if lines else "没有找到用户。"

    def format_trending_tags(self, resp, limit=30):
        tags = resp.get("trend_tags", []) if isinstance(resp, dict) else []
        lines = []
        for i, x in enumerate(tags[:limit], 1):
            tag = getv(x, "tag", "")
            trans = getv(x, "translated_name", "")
            if not tag:
                continue
            suffix = f"（{trans}）" if trans else ""
            lines.append(f"{i}. {tag}{suffix}")
        return "Pixivc 热门标签：\n" + "\n".join(lines) if lines else "没有找到热门标签。"

    async def collect_paginated_illust(self, method_name: str, count: int, *args, **kwargs):
        api = await self.api()
        c = self.cfg()
        items = []
        next_qs = None
        max_pages = 1000 if c["search_pages"] == -1 else max(1, c["search_pages"])
        start_page = self.effective_start_page()
        for page in range(max_pages + start_page - 1):
            if next_qs:
                resp = await self.api_call(method_name, **next_qs)
            else:
                resp = await self.api_call(method_name, *args, **kwargs)
            current_page = page + 1
            if current_page >= start_page:
                batch = [x for x in extract_items(resp, "illust") if self.pass_filter(x, "illust")]
                items = unique_items(items + batch)
                if len(items) >= count:
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                break
        return items[:count]

    async def collect_paginated_novel(self, method_name: str, count: int, *args, **kwargs):
        api = await self.api()
        c = self.cfg()
        items = []
        next_qs = None
        max_pages = 1000 if c["search_pages"] == -1 else max(1, c["search_pages"])
        start_page = self.effective_start_page()
        for page in range(max_pages + start_page - 1):
            if next_qs:
                resp = await self.api_call(method_name, **next_qs)
            else:
                resp = await self.api_call(method_name, *args, **kwargs)
            current_page = page + 1
            if current_page >= start_page:
                batch = [x for x in extract_items(resp, "novel") if self.pass_filter(x, "novel")]
                items = unique_items(items + batch)
                if len(items) >= count:
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                break
        return items[:count]

    async def collect_paginated_users(self, method_name: str, count: int, *args, **kwargs):
        api = await self.api()
        c = self.cfg()
        users = []
        next_qs = None
        max_pages = 1000 if c["search_pages"] == -1 else max(1, c["search_pages"])
        start_page = self.effective_start_page()
        for page in range(max_pages + start_page - 1):
            if next_qs:
                resp = await self.api_call(method_name, **next_qs)
            else:
                resp = await self.api_call(method_name, *args, **kwargs)
            current_page = page + 1
            if current_page >= start_page:
                users += self.extract_users(resp)
                if len(users) >= count:
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                break
        return users[:count]

    def require_admin_feature(self, event: AstrMessageEvent, key: str) -> bool:
        c = self.cfg()
        if not bool(c.get(key, True)):
            return True
        return self.is_bot_admin(event)

    def admin_denied_text(self):
        return "抱歉，只有 bot 管理者可以使用该 Pixiv 功能。"

    def require_write_permission(self, event: AstrMessageEvent) -> bool:
        return self.is_bot_admin(event)

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

    @filter.command("pixivc_auto")
    async def pixivc_auto(self, event: AstrMessageEvent, args: str = ""):
        q = full_command_args(event, "pixivc_auto", args)
        if not q:
            yield event.plain_result("用法：/pixivc_auto 关键词")
            return
        for attempt in range(2):
            try:
                tags = await self.pixiv_autocomplete(q)
                yield event.plain_result(self.format_autocomplete(tags, 20))
                return
            except Exception as e:
                if attempt == 0 and self._looks_auth_failed(exc=e):
                    await self.refresh_api_silent()
                    logger.info("Pixivc 已静默刷新 access token，正在自动重试本次自动补全命令。")
                    continue
                logger.error(f"pixivc autocomplete failed: {e}", exc_info=True)
                yield event.plain_result(f"自动补全失败：{e}")
                return

    @filter.command("pixivc_illust_id")
    async def pixivc_illust_id(self, event: AstrMessageEvent, args: str = ""):
        q = full_command_args(event, "pixivc_illust_id", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_illust_id 作品ID")
            return
        async for r in self.run_illust_job(event, f"illust_{q}", lambda: self._collect_illust_detail(q)):
            yield r

    async def _collect_illust_detail(self, illust_id: str):
        resp = await self.api_call("illust_detail", int(illust_id))
        item = self.extract_first_illust(resp)
        if not item or not self.pass_filter(item, "illust"):
            return []
        return [item]

    @filter.command("pixivc_bookmark_add")
    async def pixivc_bookmark_add(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_bookmark"):
            yield event.plain_result(self.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_bookmark_add", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_bookmark_add 作品ID")
            return
        await self.api_call("illust_bookmark_add", int(q), restrict="public")
        yield event.plain_result("已收藏作品。")

    @filter.command("pixivc_bookmark_del")
    async def pixivc_bookmark_del(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_bookmark"):
            yield event.plain_result(self.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_bookmark_del", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_bookmark_del 作品ID")
            return
        await self.api_call("illust_bookmark_delete", int(q))
        yield event.plain_result("已取消收藏作品。")

    @filter.command("pixivc_bookmarks")
    async def pixivc_bookmarks(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_bookmarks"):
            yield event.plain_result(self.admin_denied_text())
            return
        _, count = self.parse_query_count(full_command_args(event, "pixivc_bookmarks", args))
        async for r in self.run_illust_job(event, "my_bookmarks", lambda: self._collect_my_bookmarks(count)):
            yield r

    async def _get_api_user_id(self):
        api = await self.api()
        try:
            return int(getattr(api, "user_id", None) or 0)
        except Exception:
            return 0

    async def _collect_my_bookmarks(self, count: int):
        uid = await self._get_api_user_id()
        if not uid:
            raise RuntimeError("无法获取当前 Pixiv 用户ID，请检查 refresh_token。")
        return await self.collect_paginated_illust("user_bookmarks_illust", count, uid)

    async def _collect_my_following(self, count: int):
        uid = await self._get_api_user_id()
        if not uid:
            raise RuntimeError("无法获取当前 Pixiv 用户ID，请检查 refresh_token。")
        return await self.collect_paginated_users("user_following", count, uid)

    @filter.command("pixivc_trending_tags")
    async def pixivc_trending_tags(self, event: AstrMessageEvent):
        resp = await self.api_call("trending_tags_illust")
        yield event.plain_result(self.format_trending_tags(resp, 30))

    @filter.command("pixivc_related")
    async def pixivc_related(self, event: AstrMessageEvent, args: str = ""):
        q, count = self.parse_query_count(full_command_args(event, "pixivc_related", args))
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_related 作品ID [数量]")
            return
        async for r in self.run_illust_job(event, f"related_{q}", lambda: self.collect_paginated_illust("illust_related", count, int(q))):
            yield r

    @filter.command("pixivc_follow_add")
    async def pixivc_follow_add(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_follow"):
            yield event.plain_result(self.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_follow_add", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_follow_add 用户ID")
            return
        await self.api_call("user_follow_add", int(q), restrict="public")
        yield event.plain_result("已关注作者。")

    @filter.command("pixivc_follow_del")
    async def pixivc_follow_del(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_follow"):
            yield event.plain_result(self.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_follow_del", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_follow_del 用户ID")
            return
        await self.api_call("user_follow_delete", int(q))
        yield event.plain_result("已取消关注作者。")

    @filter.command("pixivc_following")
    async def pixivc_following(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_following"):
            yield event.plain_result(self.admin_denied_text())
            return
        _, count = self.parse_query_count(full_command_args(event, "pixivc_following", args))
        users = await self._collect_my_following(count)
        yield event.plain_result(self.format_users(users, count))

    @filter.command("pixivc_follow_latest")
    async def pixivc_follow_latest(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_follow_latest"):
            yield event.plain_result(self.admin_denied_text())
            return
        _, count = self.parse_query_count(full_command_args(event, "pixivc_follow_latest", args))
        async for r in self.run_illust_job(event, "follow_latest", lambda: self.collect_paginated_illust("illust_follow", count, restrict="public")):
            yield r

    @filter.command("pixivc_new")
    async def pixivc_new(self, event: AstrMessageEvent, args: str = ""):
        _, count = self.parse_query_count(full_command_args(event, "pixivc_new", args))
        async for r in self.run_illust_job(event, "new", lambda: self.collect_paginated_illust("illust_new", count, content_type="illust")):
            yield r

    @filter.command("pixivc_recommended_users")
    async def pixivc_recommended_users(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_recommended_users"):
            yield event.plain_result(self.admin_denied_text())
            return
        _, count = self.parse_query_count(full_command_args(event, "pixivc_recommended_users", args))
        users = await self.collect_paginated_users("user_recommended", count)
        yield event.plain_result(self.format_users(users, count))

    @filter.command("pixivc_user_search")
    async def pixivc_user_search(self, event: AstrMessageEvent, args: str = ""):
        q, count = self.parse_query_count(full_command_args(event, "pixivc_user_search", args))
        if not q:
            yield event.plain_result("用法：/pixivc_user_search 关键词 [数量]")
            return
        users = await self.collect_paginated_users("search_user", count, q)
        yield event.plain_result(self.format_users(users, count))

    @filter.command("pixivc_status")
    async def pixivc_status(self, event: AstrMessageEvent):
        c = self.cfg()
        yield event.plain_result(
            "Pixivc 状态：\n"
            f"refresh_token：{'已设置' if c['refresh_token'] else '未设置'}\n"
            f"proxy：{c['proxy'] or '未设置'}\n"
            f"use_image_proxy_without_proxy：{c['use_image_proxy_without_proxy']}\n"
            f"image_proxy_host：{c['image_proxy_host']}\n"
            f"default_count：{c['default_count']}\n"
            f"max_count：{c['max_count']}\n"
            f"search_start_page：{c['search_start_page']}\n"
            f"image_quality：{c['image_quality']}\n"
            f"allow_r18_group：{c['allow_r18_group']}\n"
            f"allow_r18_private：{c['allow_r18_private']}\n"
            f"r18白名单人数：{len(self.load_r18_whitelist())}\n"
            f"send_mode：{c['send_mode']}\n"
            f"novel_send_mode：{c['novel_send_mode']}\n"
            f"download_dir：{c['download_dir']}\n"
            f"auto_clean_enabled：{c['auto_clean_enabled']}\n"
            f"auto_clean_time：{c['auto_clean_hour']:02d}:{c['auto_clean_minute']:02d}\n"
            f"admin_discovery：{c['admin_discovery']}\n"
            f"admin_bookmark：{c['admin_bookmark']}\n"
            f"admin_follow：{c['admin_follow']}\n"
            f"admin_novel_recommended：{c['admin_novel_recommended']}\n"
            f"任务中：{self._task_lock.locked()}"
        )

    @filter.command("pixivc_get_zip")
    async def pixivc_get_zip(self, event: AstrMessageEvent, args: str = ""):
        data = self.load_last_zip()
        item_data = self.load_last_items()
        last_kind = (item_data.get("kind") or data.get("kind") or "illust") if (item_data or data) else "illust"
        # 已有 ZIP 且类型匹配时直接发送
        if data and (not item_data or data.get("kind", last_kind) == last_kind):
            path = Path(data["path"])
            async for r in self.send_zip(event, path):
                yield r
            return
        if not item_data:
            yield event.plain_result("没有可打包的 Pixivc 结果，请先执行一次图片或小说搜索。")
            return
        items = item_data.get("items") or []
        label = item_data.get("label") or "last"
        kind = item_data.get("kind") or "illust"
        if self._task_lock.locked():
            yield event.plain_result("已有 Pixiv 爬取任务正在执行，请稍后再试。")
            return
        async with self._task_lock:
            try:
                if kind == "novel":
                    yield event.plain_result("正在打包小说 ZIP，请稍等。")
                    base, zip_path, files, infos = await self.prepare_novel_files(items, "pixivc_novel_" + str(label))
                    self.save_last_zip(event, zip_path, label, len(items), kind="novel")
                    async for r in self.send_zip(event, zip_path):
                        yield r
                    shutil.rmtree(base, ignore_errors=True)
                else:
                    yield event.plain_result("正在下载 original 并打包图片 ZIP，请稍等。")
                    base, zip_path, saved = await self.prepare_original_zip_from_items(items, "pixivc_original_" + str(label))
                    if not saved:
                        yield event.plain_result("original 下载失败，请检查代理或 Pixiv 访问。")
                        return
                    self.save_last_zip(event, zip_path, label, len(saved), kind="illust")
                    async for r in self.send_zip(event, zip_path):
                        yield r
                    shutil.rmtree(base, ignore_errors=True)
            except Exception as e:
                logger.error(f"pixivc get zip failed: {e}", exc_info=True)
                yield event.plain_result(f"ZIP 打包失败：{e}")

    @filter.command("pixivc_r18_add")
    async def pixivc_r18_add(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_r18_manage"):
            yield event.plain_result(self.admin_denied_text())
            return
        qq = self.extract_qq_arg(event, "pixivc_r18_add", args)
        if not qq:
            yield event.plain_result("用法：/pixivc_r18_add QQ 或 @某人")
            return
        data = self.load_r18_whitelist()
        if qq not in data:
            data.append(qq)
        self.save_r18_whitelist(data)
        yield event.plain_result(f"已加入 Pixivc R18 白名单：{qq}")

    @filter.command("pixivc_r18_del")
    async def pixivc_r18_del(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_r18_manage"):
            yield event.plain_result(self.admin_denied_text())
            return
        qq = self.extract_qq_arg(event, "pixivc_r18_del", args)
        if not qq:
            yield event.plain_result("用法：/pixivc_r18_del QQ 或 @某人")
            return
        data = [x for x in self.load_r18_whitelist() if x != qq]
        self.save_r18_whitelist(data)
        yield event.plain_result(f"已移出 Pixivc R18 白名单：{qq}")

    @filter.command("pixivc_r18_list")
    async def pixivc_r18_list(self, event: AstrMessageEvent):
        if not self.require_admin_feature(event, "admin_r18_manage"):
            yield event.plain_result(self.admin_denied_text())
            return
        data = self.load_r18_whitelist()
        if not data:
            yield event.plain_result("Pixivc R18 白名单：空")
        else:
            yield event.plain_result("Pixivc R18 白名单：\n" + "\n".join(data))

    @filter.command("pixivc_clean")
    async def pixivc_clean(self, event: AstrMessageEvent):
        if not self.require_admin_feature(event, "admin_clean"):
            yield event.plain_result(self.admin_denied_text())
            return
        ok = await self.clean_download_cache(reason="manual_command")
        if ok:
            yield event.plain_result("Pixivc 下载缓存已清理。")
        else:
            yield event.plain_result("当前有 Pixiv 爬取任务正在执行，已跳过清理。")

    @filter.command("pixivc_key")
    async def pixivc_key(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_key", args)
        q, count = self.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_key 关键词 [数量]")
            return
        async for r in self.run_illust_job(event, f"key_{q}", lambda: self.collect_and_or([q], count, "illust", "key", "single")):
            yield r

    @filter.command("pixivc_tag")
    async def pixivc_tag(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_tag", args)
        q, count = self.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_tag 标签 [数量]")
            return
        async for r in self.run_illust_job(event, f"tag_{q}", lambda: self.collect_and_or([q], count, "illust", "tag", "single")):
            yield r

    @filter.command("pixivc_key_and")
    async def pixivc_key_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_key_and", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_key_and 关键词1,关键词2 [数量]")
            return
        async for r in self.run_illust_job(event, f"key_and_{q}", lambda: self.collect_and_or(terms, count, "illust", "key", "and")):
            yield r

    @filter.command("pixivc_key_or")
    async def pixivc_key_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_key_or", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_key_or 关键词1,关键词2 [数量]")
            return
        async for r in self.run_illust_job(event, f"key_or_{q}", lambda: self.collect_and_or(terms, count, "illust", "key", "or")):
            yield r

    @filter.command("pixivc_tag_and")
    async def pixivc_tag_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_tag_and", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_tag_and 标签1,标签2 [数量]")
            return
        async for r in self.run_illust_job(event, f"tag_and_{q}", lambda: self.collect_and_or(terms, count, "illust", "tag", "and")):
            yield r

    @filter.command("pixivc_tag_or")
    async def pixivc_tag_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_tag_or", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_tag_or 标签1,标签2 [数量]")
            return
        async for r in self.run_illust_job(event, f"tag_or_{q}", lambda: self.collect_and_or(terms, count, "illust", "tag", "or")):
            yield r

    @filter.command("pixivc_rank")
    async def pixivc_rank(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_rank", args)
        q, count = self.parse_query_count(args or "daily")
        rank_mode = q or "daily"
        async for r in self.run_illust_job(event, f"rank_{rank_mode}", lambda: self.collect_rank(rank_mode, count, "illust")):
            yield r

    @filter.command("pixivc_user")
    async def pixivc_user(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_user", args)
        q, count = self.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_user 用户ID [数量]")
            return
        async for r in self.run_illust_job(event, f"user_{q}", lambda: self.collect_user(q, count, "illust")):
            yield r

    @filter.command("pixivc_discovery")
    async def pixivc_discovery(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_discovery"):
            yield event.plain_result(self.admin_denied_text())
            return
        args = full_command_args(event, "pixivc_discovery", args)
        _, count = self.parse_query_count(args)
        async for r in self.run_illust_job(event, "discovery", lambda: self.collect_discovery(count)):
            yield r

    @filter.command("pixivc_novel_key")
    async def pixivc_novel_key(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_key", args)
        q, count = self.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_novel_key 关键词 [数量]")
            return
        async for r in self.run_novel_job(event, f"key_{q}", lambda: self.collect_and_or([q], count, "novel", "key", "single")):
            yield r

    @filter.command("pixivc_novel_tag")
    async def pixivc_novel_tag(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_tag", args)
        q, count = self.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_novel_tag 标签 [数量]")
            return
        async for r in self.run_novel_job(event, f"tag_{q}", lambda: self.collect_and_or([q], count, "novel", "tag", "single")):
            yield r

    @filter.command("pixivc_novel_key_and")
    async def pixivc_novel_key_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_key_and", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_key_and 关键词1,关键词2 [数量]")
            return
        async for r in self.run_novel_job(event, f"key_and_{q}", lambda: self.collect_and_or(terms, count, "novel", "key", "and")):
            yield r

    @filter.command("pixivc_novel_key_or")
    async def pixivc_novel_key_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_key_or", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_key_or 关键词1,关键词2 [数量]")
            return
        async for r in self.run_novel_job(event, f"key_or_{q}", lambda: self.collect_and_or(terms, count, "novel", "key", "or")):
            yield r

    @filter.command("pixivc_novel_tag_and")
    async def pixivc_novel_tag_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_tag_and", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_tag_and 标签1,标签2 [数量]")
            return
        async for r in self.run_novel_job(event, f"tag_and_{q}", lambda: self.collect_and_or(terms, count, "novel", "tag", "and")):
            yield r

    @filter.command("pixivc_novel_tag_or")
    async def pixivc_novel_tag_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_tag_or", args)
        q, count = self.parse_query_count(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_tag_or 标签1,标签2 [数量]")
            return
        async for r in self.run_novel_job(event, f"tag_or_{q}", lambda: self.collect_and_or(terms, count, "novel", "tag", "or")):
            yield r

    @filter.command("pixivc_novel_recommended", alias={"pixivc_novel_discovery"})
    async def pixivc_novel_recommended(self, event: AstrMessageEvent, args: str = ""):
        if not self.require_admin_feature(event, "admin_novel_recommended"):
            yield event.plain_result(self.admin_denied_text())
            return
        args = full_command_args(event, "pixivc_novel_recommended", args)
        _, count = self.parse_query_count(args)
        async for r in self.run_novel_job(event, "recommended", lambda: self.collect_paginated_novel("novel_recommended", count)):
            yield r

    @filter.command("pixivc_novel_rank")
    async def pixivc_novel_rank(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_rank", args)
        q, count = self.parse_query_count(args or "daily")
        rank_mode = q or "daily"
        async for r in self.run_novel_job(event, f"rank_{rank_mode}", lambda: self.collect_rank(rank_mode, count, "novel")):
            yield r

    @filter.command("pixivc_novel_user")
    async def pixivc_novel_user(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_user", args)
        q, count = self.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_novel_user 用户ID [数量]")
            return
        async for r in self.run_novel_job(event, f"user_{q}", lambda: self.collect_user(q, count, "novel")):
            yield r

    @filter.command("pixivc_novel_id")
    async def pixivc_novel_id(self, event: AstrMessageEvent, novel_id: str = ""):
        novel_id = full_command_args(event, "pixivc_novel_id", novel_id)
        novel_id = str(novel_id or "").strip()
        if not novel_id.isdigit():
            yield event.plain_result("用法：/pixivc_novel_id 小说ID")
            return
        async def collector():
            api = await self.api()
            resp = await self.api_call("novel_detail", int(novel_id))
            novel = getv(resp, "novel", None)
            return [novel] if novel and self.pass_filter(novel, "novel") else []
        async for r in self.run_novel_job(event, f"id_{novel_id}", collector):
            yield r
