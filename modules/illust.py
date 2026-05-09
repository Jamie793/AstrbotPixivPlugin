from astrbot.api import logger
from .base import BaseService
from .errors import PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE, PixivRefreshTokenInvalidError
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)


class IllustService(BaseService):
    async def collect_page_search(self, api, query, count, kind="illust", target="partial_match_for_tags", tag_terms=None):
        self._last_requested_count = count
        c = self.config_service.cfg()
        items = []
        next_qs = None
        max_pages = self.query.effective_search_max_depth()
        start_page = self.query.effective_start_page()
        reached_limit = True
        for page in range(max_pages + start_page - 1):
            if kind == "illust":
                if next_qs:
                    resp = await self.auth.api_call("search_illust", **next_qs)
                else:
                    resp = await self.auth.api_call("search_illust", query, search_target=target, sort="date_desc")
            else:
                if next_qs:
                    resp = await self.auth.api_call("search_novel", **next_qs)
                else:
                    resp = await self.auth.api_call("search_novel", query, search_target=target, sort="date_desc")
            current_page = page + 1
            if current_page >= start_page:
                raw_batch = extract_items(resp, kind)
                reasons = {"r18": 0, "ai": 0, "bookmarks": 0, "views": 0, "likes": 0, "tag": 0}
                batch = []
                for x in raw_batch:
                    reason = self.permissions.filter_reason(x, kind)
                    if reason == "pass":
                        if self.query.match_tag_filter(x, tag_terms):
                            batch.append(x)
                        else:
                            reasons["tag"] += 1
                    elif reason in reasons:
                        reasons[reason] += 1
                items = unique_items(items + batch)
                self.query.set_debug_info(f"{kind} 搜索分页", resp, len(raw_batch), len(items), reasons)
                if len(items) >= count:
                    reached_limit = False
                    self.query.set_collect_end_reason("已找到请求数量")
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                reached_limit = False
                self.query.set_collect_end_reason("Pixiv 没有下一页")
                break
        if reached_limit and len(items) < count:
            self.query.set_collect_end_reason(f"达到最大搜索深度 {max_pages}")
        return items[:count]

    async def collect_and_or(self, terms, count, kind="illust", mode="key", logic="single", tag_terms=None):
        self._last_requested_count = count
        api = await self.auth.api()
        c = self.config_service.cfg()
        target = c["tag_search_target"] if mode == "tag" else c["keyword_search_target"]
        if target == "keyword":
            target = "partial_match_for_tags"
        if logic == "or":
            all_items = []
            for term in terms:
                exact_tags = self.query.merge_tag_filters([term], tag_terms) if mode == "tag" else tag_terms
                all_items += await self.collect_page_search(api, term, count, kind, target, exact_tags)
            items = unique_items(all_items)
            # tag_or 是 OR：每一路搜索已按对应单标签精确过滤，这里只去重截断。
            return items[:count]
        query = terms[0] if terms else ""
        exact_tags = self.query.merge_tag_filters(terms, tag_terms) if mode == "tag" else tag_terms
        fetch_count = count * 3 if mode == "tag" else (count * 2 if logic == "and" else count)
        items = await self.collect_page_search(api, query, fetch_count, kind, target, exact_tags)
        # tag / tag_and 搜索必须最终再按作品 tags 做单标签精确过滤，避免 Pixiv 返回近似标签。
        if mode == "tag":
            items = [x for x in items if self.query.match_tag_filter(x, exact_tags)]
        elif logic == "and" and c["and_filter_strict"]:
            items = [x for x in items if self.query.and_match(x, terms, mode)]
        return items[:count]

    async def collect_rank(self, rank_mode, count, kind="illust", tag_terms=None):
        self._last_requested_count = count
        mode_map = {"daily": "day", "day": "day", "weekly": "week", "week": "week", "monthly": "month", "month": "month", "rookie": "rookie"}
        rank_mode = mode_map.get(str(rank_mode or "daily").lower(), str(rank_mode or "day"))
        if kind == "illust":
            return await self.collect_paginated_illust("illust_ranking", count, mode=rank_mode, tag_terms=tag_terms)
        # pixivpy3 当前没有 novel_ranking，小说榜第一版降级为推荐小说。
        # 保留 /pixivc_novel_rank 命令入口，后续可替换为 Web API 榜单实现。
        return await self.novel.collect_paginated_novel("novel_recommended", count, tag_terms=tag_terms)

    async def collect_user(self, user_id, count, kind="illust", tag_terms=None):
        self._last_requested_count = count
        if not str(user_id).isdigit():
            raise RuntimeError("用户ID必须是数字")
        if kind == "illust":
            return await self.collect_paginated_illust("user_illusts", count, int(user_id), type="illust", tag_terms=tag_terms)
        return await self.novel.collect_paginated_novel("user_novels", count, int(user_id), tag_terms=tag_terms)

    async def collect_discovery(self, count, tag_terms=None):
        self._last_requested_count = count
        api = await self.auth.api()
        items = []
        next_qs = None
        max_pages = self.query.effective_search_max_depth()
        reached_limit = True
        for _ in range(max_pages):
            if next_qs:
                resp = await self.auth.api_call("illust_recommended", **next_qs)
            else:
                resp = await self.auth.api_call("illust_recommended", include_ranking_illusts=True)
            raw_batch = extract_items(resp, "illust")
            reasons = {"r18": 0, "ai": 0, "bookmarks": 0, "views": 0, "likes": 0, "tag": 0}
            batch = []
            for x in raw_batch:
                reason = self.permissions.filter_reason(x, "illust")
                if reason == "pass":
                    if self.query.match_tag_filter(x, tag_terms):
                        batch.append(x)
                    else:
                        reasons["tag"] += 1
                elif reason in reasons:
                    reasons[reason] += 1
            items = unique_items(items + batch)
            self.query.set_debug_info("illust 发现分页", resp, len(raw_batch), len(items), reasons)
            if len(items) >= count:
                reached_limit = False
                self.query.set_collect_end_reason("已找到请求数量")
                break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                reached_limit = False
                self.query.set_collect_end_reason("Pixiv 没有下一页")
                break
        if reached_limit and len(items) < count:
            self.query.set_collect_end_reason(f"达到最大搜索深度 {max_pages}")
        return items[:count]

    def extract_first_illust(self, resp):
        if isinstance(resp, dict):
            item = resp.get("illust") or resp.get("illustration")
            if item:
                return item
        return None

    async def collect_paginated_illust(self, method_name: str, count: int, *args, tag_terms=None, **kwargs):
        self._last_requested_count = count
        api = await self.auth.api()
        c = self.config_service.cfg()
        items = []
        next_qs = None
        max_pages = self.query.effective_search_max_depth()
        start_page = self.query.effective_start_page()
        reached_limit = True
        for page in range(max_pages + start_page - 1):
            if next_qs:
                resp = await self.auth.api_call(method_name, **next_qs)
            else:
                resp = await self.auth.api_call(method_name, *args, **kwargs)
            current_page = page + 1
            if current_page >= start_page:
                raw_batch = extract_items(resp, "illust")
                reasons = {"r18": 0, "ai": 0, "bookmarks": 0, "views": 0, "likes": 0, "tag": 0}
                batch = []
                for x in raw_batch:
                    reason = self.permissions.filter_reason(x, "illust")
                    if reason == "pass":
                        if self.query.match_tag_filter(x, tag_terms):
                            batch.append(x)
                        else:
                            reasons["tag"] += 1
                    elif reason in reasons:
                        reasons[reason] += 1
                items = unique_items(items + batch)
                self.query.set_debug_info(f"{method_name} 分页", resp, len(raw_batch), len(items), reasons)
                if len(items) >= count:
                    reached_limit = False
                    self.query.set_collect_end_reason("已找到请求数量")
                    break
            try:
                next_qs = api.parse_qs(getv(resp, "next_url", None))
            except Exception:
                next_qs = None
            if not next_qs:
                reached_limit = False
                self.query.set_collect_end_reason("Pixiv 没有下一页")
                break
        if reached_limit and len(items) < count:
            self.query.set_collect_end_reason(f"达到最大搜索深度 {max_pages}")
        return items[:count]

    async def run_illust_job(self, event, label, collector):
        if self._task_lock.locked():
            yield event.plain_result("已有 Pixiv 爬取任务正在执行，请稍后再试。")
            return
        async with self._task_lock:
            c = self.config_service.cfg()
            c["download_dir"].mkdir(parents=True, exist_ok=True)
            self._current_allow_r18 = self.permissions.allow_r18_for_event(event)
            try:
                for attempt in range(2):
                    try:
                        if attempt == 0:
                            yield event.plain_result(f"开始爬取 Pixiv：{label}。")
                        else:
                            logger.info("Pixivc 已静默刷新 access token，正在自动重试本次图片命令。")
                        self._last_requested_count = None
                        self._last_collect_end_reason = "未知原因"
                        items = await collector()
                        requested_count = int(self._last_requested_count or len(items) or c["default_count"])
                        if not items:
                            yield event.plain_result(f"没有找到符合条件的作品。原因：{self.query.collect_end_reason_text()}。" + ("\n" + self._last_debug if self._last_debug else ""))
                            return
                        if len(items) < requested_count:
                            yield event.plain_result(f"只找到 {len(items)}/{requested_count} 个符合条件的作品。原因：{self.query.collect_end_reason_text()}。" + ("\n" + self._last_debug if self._last_debug else ""))
                        self.cache.save_last_items(event, items, label, "illust")
                        base, zip_path, saved = await self.downloader.prepare_illust_files(items, "pixivc_preview_" + label, make_zip=False)
                        if not saved:
                            yield event.plain_result("找到作品但图片下载失败，请检查代理或 Pixiv 访问。")
                            return
                        try:
                            zip_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        requested_count = len(items)
                        work_count = len({item_id(item) for _, item, _, _ in saved})
                        image_count = len(saved)
                        extra = ""
                        if work_count < requested_count:
                            extra = "\n注意：部分作品图片下载失败，实际发送作品数少于已找到作品数。"
                        limit_notice = getattr(self, "_last_count_limit_notice", "") or ""
                        limit_text = f"{limit_notice}" if limit_notice else ""
                        yield event.plain_result(f"下载完成：{work_count} 个作品，共 {image_count} 张图片。{limit_text}状态：{self.query.collect_end_reason_text()}。正在发送图片合并转发预览。需要 original ZIP 请发送 /pixivc_get_zip" + extra)
                        async for r in self.sender.dispatch_illust_result(event, base, zip_path, saved):
                            yield r
                        return
                    except PixivRefreshTokenInvalidError as e:
                        yield event.plain_result(str(e))
                        return
                    except Exception as e:
                        if attempt == 0 and self.auth._looks_auth_failed(exc=e):
                            await self.auth.refresh_api_silent()
                            continue
                        logger.error(f"pixivc illust job failed: {e}", exc_info=True)
                        yield event.plain_result(f"爬取失败：{e}")
                        return
            finally:
                self._current_allow_r18 = None

    async def _collect_illust_detail(self, illust_id: str):
        resp = await self.auth.api_call("illust_detail", int(illust_id))
        item = self.extract_first_illust(resp)
        if not item or not self.permissions.pass_filter(item, "illust"):
            return []
        return [item]

    async def _collect_my_bookmarks(self, count: int, tag_terms=None):
        uid = await self.social._get_api_user_id()
        if not uid:
            raise RuntimeError("无法获取当前 Pixiv 用户ID，请检查 refresh_token。")
        return await self.collect_paginated_illust("user_bookmarks_illust", count, uid, tag_terms=tag_terms)

    async def _collect_my_following(self, count: int):
        uid = await self.social._get_api_user_id()
        if not uid:
            raise RuntimeError("无法获取当前 Pixiv 用户ID，请检查 refresh_token。")
        return await self.social.collect_paginated_users("user_following", count, uid)
