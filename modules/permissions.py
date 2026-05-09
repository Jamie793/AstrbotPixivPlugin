import re
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At
from .base import BaseService
from .paths import R18_WHITELIST_FILE
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)

class PermissionService(BaseService):
    def sender_id(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id() or "").strip()
        except Exception:
            pass
        try:
            return str(getattr(getattr(event, "message_obj", None), "sender_id", "") or "").strip()
        except Exception:
            return ""

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
        try:
            fn = getattr(event, "is_admin", None)
            if callable(fn):
                return bool(fn())
        except Exception:
            return False
        return False

    def allow_r18_for_event(self, event: AstrMessageEvent) -> bool:
        c = self.config_service.cfg()
        switch_on = c["allow_r18_group"] if self.is_group_event(event) else c["allow_r18_private"]
        if not switch_on:
            return False
        if self.is_bot_admin(event):
            return True
        sender = self.sender_id(event)
        return bool(sender and sender in self.load_r18_whitelist())

    def is_r18_query_term(self, text: str) -> bool:
        raw = str(text or "").strip().lower()
        if not raw:
            return False
        compact = re.sub(r"[\s_\-]+", "", raw)
        return compact in {"r18", "r18g", "18禁"} or raw in {"r-18", "r-18g", "r18", "r18g", "18禁"}

    def contains_r18_query(self, *values) -> bool:
        for value in values:
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                if self.contains_r18_query(*list(value)):
                    return True
                continue
            text = str(value or "")
            if text.strip().startswith("-"):
                continue
            candidates = []
            candidates.append(text)
            candidates.extend(split_terms(text))
            candidates.extend([x for x in re.split(r"\s+", text) if x])
            if any(self.is_r18_query_term(x) for x in candidates):
                return True
        return False

    def r18_query_denied_text(self):
        return "检测到 R18 标签/关键词，但你当前没有 R18 查看权限。请确认对应场景 R18 开关已开启，并且发送者在 R18 白名单内。"

    def require_r18_query_allowed(self, event: AstrMessageEvent, *values):
        if not self.contains_r18_query(*values):
            return ""
        if self.allow_r18_for_event(event):
            return ""
        return self.r18_query_denied_text()

    def pass_filter(self, item, kind="illust"):
        c = self.config_service.cfg()
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

    def filter_reason(self, item, kind="illust"):
        c = self.config_service.cfg()
        allow_r18 = self._current_allow_r18 if self._current_allow_r18 is not None else False
        if not allow_r18 and is_r18(item):
            return "r18"
        if not c["allow_ai"] and is_ai(item):
            return "ai"
        if c["min_bookmarks"] >= 0 and stat_value(item, "total_bookmarks") < c["min_bookmarks"]:
            return "bookmarks"
        if c["min_views"] >= 0 and stat_value(item, "total_view", "total_views") < c["min_views"]:
            return "views"
        if c["min_likes"] >= 0 and stat_value(item, "total_like", "total_likes", "like_count", "likeCount") < c["min_likes"]:
            return "likes"
        return "pass"

    def require_admin_feature(self, event: AstrMessageEvent, key: str) -> bool:
        c = self.config_service.cfg()
        if not bool(c.get(key, True)):
            return True
        return self.is_bot_admin(event)

    def admin_denied_text(self):
        return "抱歉，只有 bot 管理者可以使用该 Pixiv 功能。"

    def require_write_permission(self, event: AstrMessageEvent) -> bool:
        return self.is_bot_admin(event)
