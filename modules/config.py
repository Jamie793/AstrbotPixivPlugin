import os
from pathlib import Path
from .base import BaseService
from .paths import DATA_DIR, PLUGIN_DIR

class ConfigService(BaseService):
    def cfg(self):
        proxy = str(self.config.get("proxy") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
        quality = str(self.config.get("image_quality", "large") or "large").lower()
        if quality not in {"medium", "large", "original"}:
            quality = "large"
        download_dir = str(self.config.get("download_dir", "data/downloads") or "data/downloads")
        dl_path = Path(download_dir)
        if not dl_path.is_absolute():
            # 相对路径以插件目录为基准，也就是 metadata.yaml 所在目录。
            dl_path = PLUGIN_DIR / dl_path
        admin_permissions = self.config.get("admin_permissions") or {}

        def admin_perm(key: str, default: bool = True) -> bool:
            return bool(admin_permissions.get(key, self.config.get(key, default)))

        return {
            "refresh_token": str(self.config.get("refresh_token") or "").strip(),
            "refresh_token_interval_hours": max(0, int(self.config.get("refresh_token_interval_hours", 72) or 72)),
            "debug_enabled": bool(self.config.get("debug_enabled", False)),
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
            "admin_discovery": admin_perm("admin_discovery"),
            "admin_bookmark": admin_perm("admin_bookmark"),
            "admin_bookmarks": admin_perm("admin_bookmarks"),
            "admin_follow": admin_perm("admin_follow"),
            "admin_following": admin_perm("admin_following"),
            "admin_follow_latest": admin_perm("admin_follow_latest"),
            "admin_recommended_users": admin_perm("admin_recommended_users"),
            "admin_novel_recommended": admin_perm("admin_novel_recommended"),
            "admin_clean": admin_perm("admin_clean"),
            "admin_r18_manage": admin_perm("admin_r18_manage"),
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
            "zip_password_length": max(8, min(int(self.config.get("zip_password_length", 64) or 64), 64)),
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
