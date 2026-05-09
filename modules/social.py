from .base import BaseService
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)


class SocialService(BaseService):
    async def _get_api_user_id(self):
        api = await self.auth.api()
        try:
            return int(getattr(api, "user_id", None) or 0)
        except Exception:
            return 0

    async def collect_paginated_users(self, method_name: str, count: int, *args, **kwargs):
        api = await self.auth.api()
        c = self.config_service.cfg()
        users = []
        next_qs = None
        max_pages = self.query.effective_search_max_depth()
        start_page = self.query.effective_start_page()
        for page in range(max_pages + start_page - 1):
            if next_qs:
                resp = await self.auth.api_call(method_name, **next_qs)
            else:
                resp = await self.auth.api_call(method_name, *args, **kwargs)
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
