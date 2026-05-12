import asyncio
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from .base import BaseService
from .paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)

class CacheService(BaseService):
    def next_clean_time(self):
        c = self.config_service.cfg()
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
        d = DEFAULT_DOWNLOAD_DIR
        if self._task_lock.locked():
            logger.info("Pixivc 清理跳过：当前有爬取任务正在执行")
            return False
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        self.state.clear_section("last_zip")
        logger.info(f"Pixivc 整个 cache 目录已清理，reason={reason}")
        return True

    def format_size(self, size: int) -> str:
        size = max(0, int(size or 0))
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)}{unit}"
                return f"{value:.1f}{unit}"
            value /= 1024
        return f"{size}B"

    def path_total_size(self, path: Path) -> int:
        try:
            if path.is_file():
                return path.stat().st_size
            total = 0
            for x in path.rglob("*"):
                try:
                    if x.is_file():
                        total += x.stat().st_size
                except Exception:
                    continue
            return total
        except Exception:
            return 0

    def configured_cache_dir_text(self) -> str:
        try:
            return str(DEFAULT_DOWNLOAD_DIR.relative_to(DATA_DIR))
        except Exception:
            return str(DEFAULT_DOWNLOAD_DIR)

    def format_cache_list(self, limit=30):
        c = self.config_service.cfg()
        d = c["download_dir"]
        display_dir = self.configured_cache_dir_text()
        d.mkdir(parents=True, exist_ok=True)
        try:
            children = list(d.iterdir())
        except Exception as e:
            return f"读取缓存目录失败：{e}"
        entries = []
        for path in children:
            try:
                entries.append((path.stat().st_mtime, path))
            except Exception:
                continue
        entries.sort(key=lambda x: x[0], reverse=True)
        if not entries:
            return f"Pixivc 缓存列表：空\n缓存目录：{display_dir}"
        limit = max(1, int(limit or 30))
        lines = [f"Pixivc 缓存列表：{len(entries)} 项", f"缓存目录：{display_dir}"]
        for i, (mtime, path) in enumerate(entries[:limit], 1):
            kind = "目录" if path.is_dir() else "文件"
            size = self.format_size(self.path_total_size(path))
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            lines.append(f"{i}. [{kind}] {path.name} | {size} | {ts}")
        if len(entries) > limit:
            lines.append(f"还有 {len(entries) - limit} 项未显示，可用 n 调整显示数量。")
        return "\n".join(lines)

    def save_last_items(self, event: AstrMessageEvent, items, label: str, kind: str = "illust"):
        ids = []
        for item in items or []:
            iid = item_id(item)
            if iid and iid not in ids:
                ids.append(iid)
        data = {
            "kind": str(kind),
            "label": str(label),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sender_id": self.permissions.sender_id(event),
            "ids": ids,
        }
        try:
            gid = event.get_group_id()
        except Exception:
            gid = ""
        data["group_id"] = str(gid or "")
        self.state.set_section("last_items", data)
        self.state.clear_section("last_zip")

    def load_last_items(self):
        data = self.state.get_section("last_items", {})
        if not isinstance(data, dict):
            return {}
        ids = data.get("ids") or []
        # 兼容旧 state：如果仍然是完整 items，就提取 id 后返回。
        if not ids and isinstance(data.get("items"), list):
            ids = []
            for item in data.get("items") or []:
                iid = item_id(item)
                if iid and iid not in ids:
                    ids.append(iid)
            data = dict(data)
            data.pop("items", None)
            data["ids"] = ids
        if not isinstance(ids, list) or not ids:
            return {}
        return data

    def save_last_zip(self, event: AstrMessageEvent, zip_path: Path, label: str, count: int, kind: str = "illust", password: str = ""):
        data = {
            "kind": str(kind),
            "path": str(zip_path),
            "name": zip_path.name,
            "label": str(label),
            "count": int(count),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sender_id": self.permissions.sender_id(event),
            "password": str(password or ""),
        }
        try:
            gid = event.get_group_id()
        except Exception:
            gid = ""
        data["group_id"] = str(gid or "")
        self.state.set_section("last_zip", data)

    def load_last_zip(self):
        data = self.state.get_section("last_zip", {})
        if not isinstance(data, dict):
            return {}
        path = Path(str(data.get("path") or ""))
        if not path.exists() or not path.is_file():
            return {}
        data["path"] = str(path)
        return data
