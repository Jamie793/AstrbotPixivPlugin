import asyncio
import json
import shutil
from pathlib import Path

try:
    import pyzipper
except ImportError:
    pyzipper = None

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .modules.auth import AuthService
from .modules.cache import CacheService
from .modules.config import ConfigService
from .modules.downloader import DownloaderService
from .modules.illust import IllustService
from .modules.misc import MiscService
from .modules.novel import NovelService
from .modules.permissions import PermissionService
from .modules.query import QueryService
from .modules.sender import SenderService
from .modules.social import SocialService
from .modules.errors import PixivRefreshTokenInvalidError
from .modules.oauth import generate_login_url, exchange_token, token_parts
from .modules.paths import OAUTH_STATE_FILE, TOKEN_STATE_FILE
from .modules.pixiv_utils import full_command_args, getv, item_id, split_terms

@register(
    "astrbot_plugin_pixivs_crawler",
    "Jamie793",
    "一个面向 AstrBot 的 Pixiv App API 插件，支持 Pixiv 图片、漫画、小说搜索，作品详情，收藏，关注，热门标签，相关作品，自动补全，合并转发预览，以及按需下载 original 原图 ZIP",
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
        self._last_debug = ""
        self._clean_task = None
        self._refresh_token_task = None
        self.config_service = ConfigService(self)
        self.auth = AuthService(self)
        self.cache = CacheService(self)
        self.query = QueryService(self)
        self.permissions = PermissionService(self)
        self.downloader = DownloaderService(self)
        self.sender = SenderService(self)
        self.illust = IllustService(self)
        self.novel = NovelService(self)
        self.social = SocialService(self)
        self.misc = MiscService(self)

































































































    async def initialize(self):
        c = self.config_service.cfg()
        if c.get("encrypt_zip_enabled", False) and pyzipper is None:
            logger.warning("Pixivc 已开启 ZIP 加密，但缺少 pyzipper 依赖；请安装 requirements.txt 后重启插件。")
        if c["auto_clean_enabled"] and (self._clean_task is None or self._clean_task.done()):
            self._clean_task = asyncio.create_task(self.cache.auto_clean_loop())
            logger.info(f"Pixivc 每日自动清理已启用：{c['auto_clean_hour']:02d}:{c['auto_clean_minute']:02d}")
        if c["refresh_token_interval_hours"] > 0 and (self._refresh_token_task is None or self._refresh_token_task.done()):
            self._refresh_token_task = asyncio.create_task(self.auth.refresh_token_keepalive_loop())
            logger.info(f"Pixivc Refresh Token 静默刷新已启用：每 {c['refresh_token_interval_hours']} 小时。")

    async def terminate(self):
        if self._clean_task and not self._clean_task.done():
            self._clean_task.cancel()
            logger.info("Pixivc 每日自动清理任务已停止")
        if self._refresh_token_task and not self._refresh_token_task.done():
            self._refresh_token_task.cancel()
            logger.info("Pixivc Refresh Token 静默刷新任务已停止")


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
        obj = await exchange_token(text, OAUTH_STATE_FILE)
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
        yield event.plain_result(self.misc.build_help_text())


    @filter.command("pixivc_auto")
    async def pixivc_auto(self, event: AstrMessageEvent, args: str = ""):
        q = full_command_args(event, "pixivc_auto", args)
        if not q:
            yield event.plain_result("用法：/pixivc_auto 关键词")
            return
        for attempt in range(2):
            try:
                tags = await self.misc.pixiv_autocomplete(q)
                yield event.plain_result(self.misc.format_autocomplete(tags, 20))
                return
            except PixivRefreshTokenInvalidError as e:
                yield event.plain_result(str(e))
                return
            except Exception as e:
                if attempt == 0 and self.auth._looks_auth_failed(exc=e):
                    await self.auth.refresh_api_silent()
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
        async for r in self.illust.run_illust_job(event, f"illust_{q}", lambda: self.illust._collect_illust_detail(q)):
            yield r


    @filter.command("pixivc_bookmark_add")
    async def pixivc_bookmark_add(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_bookmark"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_bookmark_add", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_bookmark_add 作品ID")
            return
        await self.auth.api_call("illust_bookmark_add", int(q), restrict="public")
        yield event.plain_result("已收藏作品。")

    @filter.command("pixivc_bookmark_del")
    async def pixivc_bookmark_del(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_bookmark"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_bookmark_del", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_bookmark_del 作品ID")
            return
        await self.auth.api_call("illust_bookmark_delete", int(q))
        yield event.plain_result("已取消收藏作品。")

    @filter.command("pixivc_bookmarks")
    async def pixivc_bookmarks(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_bookmarks"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        _, count, tag_terms = self.query.parse_query_count_tags(full_command_args(event, "pixivc_bookmarks", args))
        async for r in self.illust.run_illust_job(event, "my_bookmarks", lambda: self.illust._collect_my_bookmarks(count, tag_terms)):
            yield r


    @filter.command("pixivc_trending_tags")
    async def pixivc_trending_tags(self, event: AstrMessageEvent):
        resp = await self.auth.api_call("trending_tags_illust")
        yield event.plain_result(self.social.format_trending_tags(resp, 30))

    @filter.command("pixivc_related")
    async def pixivc_related(self, event: AstrMessageEvent, args: str = ""):
        q, count, tag_terms = self.query.parse_query_count_tags(full_command_args(event, "pixivc_related", args))
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_related 作品ID")
            return
        async for r in self.illust.run_illust_job(event, f"related_{q}", lambda: self.illust.collect_paginated_illust("illust_related", count, int(q), tag_terms=tag_terms)):
            yield r

    @filter.command("pixivc_follow_add")
    async def pixivc_follow_add(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_follow"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_follow_add", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_follow_add 用户ID")
            return
        await self.auth.api_call("user_follow_add", int(q), restrict="public")
        yield event.plain_result("已关注作者。")

    @filter.command("pixivc_follow_del")
    async def pixivc_follow_del(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_follow"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        q = full_command_args(event, "pixivc_follow_del", args)
        if not q.isdigit():
            yield event.plain_result("用法：/pixivc_follow_del 用户ID")
            return
        await self.auth.api_call("user_follow_delete", int(q))
        yield event.plain_result("已取消关注作者。")

    @filter.command("pixivc_following")
    async def pixivc_following(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_following"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        _, count = self.query.parse_query_count(full_command_args(event, "pixivc_following", args))
        users = await self.illust._collect_my_following(count)
        yield event.plain_result(self.social.format_users(users, count))

    @filter.command("pixivc_follow_latest")
    async def pixivc_follow_latest(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_follow_latest"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        _, count, tag_terms = self.query.parse_query_count_tags(full_command_args(event, "pixivc_follow_latest", args))
        async for r in self.illust.run_illust_job(event, "follow_latest", lambda: self.illust.collect_paginated_illust("illust_follow", count, restrict="public", tag_terms=tag_terms)):
            yield r

    @filter.command("pixivc_new")
    async def pixivc_new(self, event: AstrMessageEvent, args: str = ""):
        _, count, tag_terms = self.query.parse_query_count_tags(full_command_args(event, "pixivc_new", args))
        async for r in self.illust.run_illust_job(event, "new", lambda: self.illust.collect_paginated_illust("illust_new", count, content_type="illust", tag_terms=tag_terms)):
            yield r

    @filter.command("pixivc_recommended_users")
    async def pixivc_recommended_users(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_recommended_users"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        _, count = self.query.parse_query_count(full_command_args(event, "pixivc_recommended_users", args))
        users = await self.social.collect_paginated_users("user_recommended", count)
        yield event.plain_result(self.social.format_users(users, count))

    @filter.command("pixivc_user_search")
    async def pixivc_user_search(self, event: AstrMessageEvent, args: str = ""):
        q, count = self.query.parse_query_count(full_command_args(event, "pixivc_user_search", args))
        if not q:
            yield event.plain_result("用法：/pixivc_user_search 关键词")
            return
        users = await self.social.collect_paginated_users("search_user", count, q)
        yield event.plain_result(self.social.format_users(users, count))

    @filter.command("pixivc_debug_last")
    async def pixivc_debug_last(self, event: AstrMessageEvent):
        yield event.plain_result(self._last_debug or "暂无调试信息。")

    @filter.command("pixivc_status")
    async def pixivc_status(self, event: AstrMessageEvent):
        c = self.config_service.cfg()
        yield event.plain_result(
            "Pixivc 状态：\n"
            f"refresh_token：{'已设置' if c['refresh_token'] else '未设置'}\n"
            f"access_token_cache：{'已保存' if TOKEN_STATE_FILE.exists() else '未保存'}\n"
            f"refresh_token_interval_hours：{c['refresh_token_interval_hours']}\n"
            f"proxy：{c['proxy'] or '未设置'}\n"
            f"use_image_proxy_without_proxy：{c['use_image_proxy_without_proxy']}\n"
            f"image_proxy_host：{c['image_proxy_host']}\n"
            f"default_count：{c['default_count']}\n"
            f"max_count：{c['max_count']}\n"
            f"search_max_depth：{c['search_max_depth']}\n"
            f"image_quality：{c['image_quality']}\n"
            f"allow_r18_group：{c['allow_r18_group']}\n"
            f"allow_r18_private：{c['allow_r18_private']}\n"
            f"r18白名单人数：{len(self.permissions.load_r18_whitelist())}\n"
            f"send_mode：{c['send_mode']}\n"
            f"novel_send_mode：{c['novel_send_mode']}\n"
            f"novel_preview_max_chars：{c['novel_preview_max_chars']}\n"
            f"novel_preview_total_chars：{c['novel_preview_total_chars']}\n"
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
        data = self.cache.load_last_zip()
        item_data = self.cache.load_last_items()
        last_kind = (item_data.get("kind") or data.get("kind") or "illust") if (item_data or data) else "illust"
        # 已有 ZIP 且类型匹配时直接发送
        if data and (not item_data or data.get("kind", last_kind) == last_kind):
            path = Path(data["path"])
            yield event.plain_result(f"检测到本地已有缓存 ZIP：{path.name}，直接发送，不重新打包。")
            async for r in self.sender.send_zip(event, path, suppress_ready=True):
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
                    prep_result = None
                    async for typ, payload in self.downloader.prepare_with_live_progress(event, items, "小说", lambda cb: self.downloader.prepare_novel_files(items, "pixivc_novel_" + str(label), progress_cb=cb)):
                        if typ == "progress":
                            yield payload
                        else:
                            prep_result = payload
                    base, zip_path, files, infos = prep_result
                    self.cache.save_last_zip(event, zip_path, label, len(items), kind="novel")
                    async for r in self.sender.send_zip(event, zip_path):
                        yield r
                    shutil.rmtree(base, ignore_errors=True)
                else:
                    yield event.plain_result("正在下载 original 并打包图片 ZIP，请稍等。")
                    prep_result = None
                    async for typ, payload in self.downloader.prepare_with_live_progress(event, items, "作品", lambda cb: self.downloader.prepare_original_zip_from_items(items, "pixivc_original_" + str(label), progress_cb=cb)):
                        if typ == "progress":
                            yield payload
                        else:
                            prep_result = payload
                    base, zip_path, saved = prep_result
                    if not saved:
                        yield event.plain_result("original 下载失败，请检查代理或 Pixiv 访问。")
                        return
                    work_count = len({item_id(item) for _, item, _, _ in saved})
                    self.cache.save_last_zip(event, zip_path, label, work_count, kind="illust")
                    async for r in self.sender.send_zip(event, zip_path):
                        yield r
                    shutil.rmtree(base, ignore_errors=True)
            except Exception as e:
                logger.error(f"pixivc get zip failed: {e}", exc_info=True)
                yield event.plain_result(f"ZIP 打包失败：{e}")

    @filter.command("pixivc_r18_add")
    async def pixivc_r18_add(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_r18_manage"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        qq = self.permissions.extract_qq_arg(event, "pixivc_r18_add", args)
        if not qq:
            yield event.plain_result("用法：/pixivc_r18_add QQ 或 @某人")
            return
        data = self.permissions.load_r18_whitelist()
        if qq not in data:
            data.append(qq)
        self.permissions.save_r18_whitelist(data)
        yield event.plain_result(f"已加入 Pixivc R18 白名单：{qq}")

    @filter.command("pixivc_r18_del")
    async def pixivc_r18_del(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_r18_manage"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        qq = self.permissions.extract_qq_arg(event, "pixivc_r18_del", args)
        if not qq:
            yield event.plain_result("用法：/pixivc_r18_del QQ 或 @某人")
            return
        data = [x for x in self.permissions.load_r18_whitelist() if x != qq]
        self.permissions.save_r18_whitelist(data)
        yield event.plain_result(f"已移出 Pixivc R18 白名单：{qq}")

    @filter.command("pixivc_r18_list")
    async def pixivc_r18_list(self, event: AstrMessageEvent):
        if not self.permissions.require_admin_feature(event, "admin_r18_manage"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        data = self.permissions.load_r18_whitelist()
        if not data:
            yield event.plain_result("Pixivc R18 白名单：空")
        else:
            yield event.plain_result("Pixivc R18 白名单：\n" + "\n".join(data))

    @filter.command("pixivc_cache")
    async def pixivc_cache(self, event: AstrMessageEvent, args: str = ""):
        _, count = self.query.parse_query_count(full_command_args(event, "pixivc_cache", args))
        yield event.plain_result(self.cache.format_cache_list(count))

    @filter.command("pixivc_clean")
    async def pixivc_clean(self, event: AstrMessageEvent):
        if not self.permissions.require_admin_feature(event, "admin_clean"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        ok = await self.cache.clean_download_cache(reason="manual_command")
        if ok:
            yield event.plain_result("Pixivc 下载缓存已清理。")
        else:
            yield event.plain_result("当前有 Pixiv 爬取任务正在执行，已跳过清理。")

    @filter.command("pixivc_key")
    async def pixivc_key(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_key", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        if not q:
            yield event.plain_result("用法：/pixivc_key 关键词")
            return
        denied = self.permissions.require_r18_query_allowed(event, q, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"key_{q}", lambda: self.illust.collect_and_or([q], count, "illust", "key", "single", tag_terms)):
            yield r

    @filter.command("pixivc_tag")
    async def pixivc_tag(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_tag", args)
        q, count = self.query.parse_query_count(args)
        if not q:
            yield event.plain_result("用法：/pixivc_tag 标签")
            return
        denied = self.permissions.require_r18_query_allowed(event, q)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"tag_{q}", lambda: self.illust.collect_and_or([q], count, "illust", "tag", "single")):
            yield r

    @filter.command("pixivc_key_and")
    async def pixivc_key_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_key_and", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_key_and 关键词1,关键词2")
            return
        denied = self.permissions.require_r18_query_allowed(event, terms, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"key_and_{q}", lambda: self.illust.collect_and_or(terms, count, "illust", "key", "and", tag_terms)):
            yield r

    @filter.command("pixivc_key_or")
    async def pixivc_key_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_key_or", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_key_or 关键词1,关键词2")
            return
        denied = self.permissions.require_r18_query_allowed(event, terms, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"key_or_{q}", lambda: self.illust.collect_and_or(terms, count, "illust", "key", "or", tag_terms)):
            yield r

    @filter.command("pixivc_tag_and")
    async def pixivc_tag_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_tag_and", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_tag_and 标签1,标签2")
            return
        denied = self.permissions.require_r18_query_allowed(event, terms, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"tag_and_{q}", lambda: self.illust.collect_and_or(terms, count, "illust", "tag", "and", tag_terms)):
            yield r

    @filter.command("pixivc_tag_or")
    async def pixivc_tag_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_tag_or", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_tag_or 标签1,标签2")
            return
        denied = self.permissions.require_r18_query_allowed(event, terms, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"tag_or_{q}", lambda: self.illust.collect_and_or(terms, count, "illust", "tag", "or", tag_terms)):
            yield r

    @filter.command("pixivc_rank")
    async def pixivc_rank(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_rank", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args or "daily")
        rank_mode = q or "daily"
        denied = self.permissions.require_r18_query_allowed(event, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"rank_{rank_mode}", lambda: self.illust.collect_rank(rank_mode, count, "illust", tag_terms)):
            yield r

    @filter.command("pixivc_user")
    async def pixivc_user(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_user", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        if not q:
            yield event.plain_result("用法：/pixivc_user 用户ID")
            return
        denied = self.permissions.require_r18_query_allowed(event, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, f"user_{q}", lambda: self.illust.collect_user(q, count, "illust", tag_terms)):
            yield r

    @filter.command("pixivc_discovery")
    async def pixivc_discovery(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_discovery"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        args = full_command_args(event, "pixivc_discovery", args)
        _, count, tag_terms = self.query.parse_query_count_tags(args)
        denied = self.permissions.require_r18_query_allowed(event, tag_terms)
        if denied:
            yield event.plain_result(denied)
            return
        async for r in self.illust.run_illust_job(event, "discovery", lambda: self.illust.collect_discovery(count, tag_terms)):
            yield r

    @filter.command("pixivc_novel_key")
    async def pixivc_novel_key(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_key", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        if not q:
            yield event.plain_result("用法：/pixivc_novel_key 关键词")
            return
        async for r in self.novel.run_novel_job(event, f"key_{q}", lambda: self.illust.collect_and_or([q], count, "novel", "key", "single", tag_terms)):
            yield r

    @filter.command("pixivc_novel_tag")
    async def pixivc_novel_tag(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_tag", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        if not q:
            yield event.plain_result("用法：/pixivc_novel_tag 标签")
            return
        async for r in self.novel.run_novel_job(event, f"tag_{q}", lambda: self.illust.collect_and_or([q], count, "novel", "tag", "single", tag_terms)):
            yield r

    @filter.command("pixivc_novel_key_and")
    async def pixivc_novel_key_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_key_and", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_key_and 关键词1,关键词2")
            return
        async for r in self.novel.run_novel_job(event, f"key_and_{q}", lambda: self.illust.collect_and_or(terms, count, "novel", "key", "and", tag_terms)):
            yield r

    @filter.command("pixivc_novel_key_or")
    async def pixivc_novel_key_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_key_or", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_key_or 关键词1,关键词2")
            return
        async for r in self.novel.run_novel_job(event, f"key_or_{q}", lambda: self.illust.collect_and_or(terms, count, "novel", "key", "or", tag_terms)):
            yield r

    @filter.command("pixivc_novel_tag_and")
    async def pixivc_novel_tag_and(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_tag_and", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_tag_and 标签1,标签2")
            return
        async for r in self.novel.run_novel_job(event, f"tag_and_{q}", lambda: self.illust.collect_and_or(terms, count, "novel", "tag", "and", tag_terms)):
            yield r

    @filter.command("pixivc_novel_tag_or")
    async def pixivc_novel_tag_or(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_tag_or", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        terms = split_terms(q)
        if not terms:
            yield event.plain_result("用法：/pixivc_novel_tag_or 标签1,标签2")
            return
        async for r in self.novel.run_novel_job(event, f"tag_or_{q}", lambda: self.illust.collect_and_or(terms, count, "novel", "tag", "or", tag_terms)):
            yield r

    @filter.command("pixivc_novel_recommended", alias={"pixivc_novel_discovery"})
    async def pixivc_novel_recommended(self, event: AstrMessageEvent, args: str = ""):
        if not self.permissions.require_admin_feature(event, "admin_novel_recommended"):
            yield event.plain_result(self.permissions.admin_denied_text())
            return
        args = full_command_args(event, "pixivc_novel_recommended", args)
        _, count, tag_terms = self.query.parse_query_count_tags(args)
        async for r in self.novel.run_novel_job(event, "recommended", lambda: self.novel.collect_paginated_novel("novel_recommended", count, tag_terms=tag_terms)):
            yield r

    @filter.command("pixivc_novel_rank")
    async def pixivc_novel_rank(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_rank", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args or "daily")
        rank_mode = q or "daily"
        async for r in self.novel.run_novel_job(event, f"rank_{rank_mode}", lambda: self.illust.collect_rank(rank_mode, count, "novel", tag_terms)):
            yield r

    @filter.command("pixivc_novel_user")
    async def pixivc_novel_user(self, event: AstrMessageEvent, args: str = ""):
        args = full_command_args(event, "pixivc_novel_user", args)
        q, count, tag_terms = self.query.parse_query_count_tags(args)
        if not q:
            yield event.plain_result("用法：/pixivc_novel_user 用户ID")
            return
        async for r in self.novel.run_novel_job(event, f"user_{q}", lambda: self.illust.collect_user(q, count, "novel", tag_terms)):
            yield r

    @filter.command("pixivc_novel_id")
    async def pixivc_novel_id(self, event: AstrMessageEvent, novel_id: str = ""):
        novel_id = full_command_args(event, "pixivc_novel_id", novel_id)
        novel_id = str(novel_id or "").strip()
        if not novel_id.isdigit():
            yield event.plain_result("用法：/pixivc_novel_id 小说ID")
            return
        async def collector():
            api = await self.auth.api()
            resp = await self.auth.api_call("novel_detail", int(novel_id))
            novel = getv(resp, "novel", None)
            return [novel] if novel and self.permissions.pass_filter(novel, "novel") else []
        async for r in self.novel.run_novel_job(event, f"id_{novel_id}", collector):
            yield r
