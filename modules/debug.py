import json
import time
import traceback
from pathlib import Path
from collections import deque
from astrbot.api import logger
from .base import BaseService
from .pixiv_utils import getv, item_id
from .paths import DATA_DIR, PLUGIN_DIR


class DebugService(BaseService):
    """Pixivc 运行期调试信息收集器。只保存摘要，不保存 token/cookie。"""

    SENSITIVE_KEYS = {"authorization", "access_token", "refresh_token", "token", "cookie", "set-cookie", "client_secret", "password"}

    def __init__(self, plugin):
        super().__init__(plugin)
        maxlen = int(getattr(plugin, "_debug_max_records", 30) or 30)
        plugin._debug_records = getattr(plugin, "_debug_records", deque(maxlen=maxlen)) or deque(maxlen=maxlen)
        plugin._debug_outputs = getattr(plugin, "_debug_outputs", deque(maxlen=maxlen)) or deque(maxlen=maxlen)
        plugin._last_api_debug = getattr(plugin, "_last_api_debug", "") or ""

    @property
    def records(self):
        return self.p._debug_records

    @property
    def outputs(self):
        return self.p._debug_outputs

    def now(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def enabled(self):
        return bool(getattr(self.p, "_debug_enabled", True))

    def _safe(self, obj, depth=0):
        if depth > 4:
            return "..."
        if obj is None or isinstance(obj, (int, float, bool)):
            return obj
        if isinstance(obj, str):
            if len(obj) > 500:
                return obj[:500] + "...(truncated)"
            return obj
        if isinstance(obj, (list, tuple, set)):
            return [self._safe(x, depth + 1) for x in list(obj)[:20]]
        if isinstance(obj, dict):
            out = {}
            for k, v in list(obj.items())[:40]:
                key = str(k)
                if key.lower() in self.SENSITIVE_KEYS or any(s in key.lower() for s in ["token", "cookie", "secret", "authorization"]):
                    out[key] = "***"
                else:
                    out[key] = self._safe(v, depth + 1)
            return out
        try:
            if hasattr(obj, "items"):
                return self._safe(dict(obj.items()), depth + 1)
        except Exception:
            pass
        try:
            if hasattr(obj, "__dict__"):
                return self._safe(vars(obj), depth + 1)
        except Exception:
            pass
        text = repr(obj)
        return text[:500] + ("...(truncated)" if len(text) > 500 else "")

    def _resp_summary(self, resp):
        summary = {"type": type(resp).__name__}
        try:
            status = getattr(resp, "status_code", None)
            if status is not None:
                summary["status_code"] = status
        except Exception:
            pass
        try:
            keys = list(resp.keys()) if hasattr(resp, "keys") else []
            if keys:
                summary["keys"] = [str(x) for x in keys[:20]]
        except Exception:
            pass
        try:
            for field in ["illusts", "novels", "user_previews", "users", "tags"]:
                vals = getv(resp, field, None)
                if vals is not None:
                    try:
                        summary[field + "_count"] = len(vals)
                    except Exception:
                        pass
                    if field in {"illusts", "novels"} and vals:
                        first = vals[0]
                        summary["first_item"] = {
                            "id": item_id(first),
                            "title": getv(first, "title", ""),
                            "x_restrict": getv(first, "x_restrict", getv(first, "restrict", "")),
                        }
        except Exception:
            pass
        try:
            next_url = getv(resp, "next_url", None)
            if next_url:
                summary["has_next_url"] = True
                summary["next_url_head"] = str(next_url)[:180]
        except Exception:
            pass
        if len(summary) <= 1:
            summary["repr"] = repr(resp)[:800]
        return summary

    def record_api(self, method_name, args=None, kwargs=None, resp=None, error=None, retried=False, raw_url=None):
        if not self.enabled():
            return
        rec = {
            "time": self.now(),
            "kind": "api",
            "method": method_name,
            "args": self._safe(list(args or [])),
            "kwargs": self._safe(dict(kwargs or {})),
            "retried": bool(retried),
        }
        if raw_url:
            rec["url"] = self._safe(raw_url)
        if error is not None:
            rec["ok"] = False
            rec["error"] = f"{type(error).__name__}: {error}"
            rec["trace_tail"] = "".join(traceback.format_exception_only(type(error), error)).strip()[-800:]
        else:
            rec["ok"] = True
            rec["response"] = self._safe(self._resp_summary(resp))
        self.records.append(rec)
        self.p._last_api_debug = self.format_record(rec)
        logger.debug(f"Pixivc debug api record: {rec.get('method')} ok={rec.get('ok')} retried={rec.get('retried')}")

    def record_output(self, text, kind="output"):
        if not self.enabled():
            return
        rec = {"time": self.now(), "kind": kind, "text": str(text or "")[:1200]}
        self.outputs.append(rec)

    def format_record(self, rec):
        return json.dumps(rec, ensure_ascii=False, indent=2, default=str)

    def format_recent(self, items, limit=5):
        arr = list(items)[-max(1, int(limit)):]
        if not arr:
            return "暂无记录。"
        return "\n\n".join(self.format_record(x) for x in arr)


    def short_path(self, path):
        try:
            p = Path(path).resolve()
            # 显示路径以插件目录为基准，即 metadata.yaml 所在目录。
            try:
                return str(p.relative_to(PLUGIN_DIR.resolve()))
            except Exception:
                pass
            return p.name
        except Exception:
            return str(path or "")

    def state_text(self):
        c = self.config_service.cfg()
        return "\n".join([
            "Pixivc 调试状态：",
            f"调试记录：{'开启' if self.enabled() else '关闭'}",
            f"配置默认：{'开启' if bool(c.get('debug_enabled', False)) else '关闭'}",
            f"API对象：{'已初始化' if self.p._api is not None else '未初始化'}",
            f"任务锁：{'忙碌' if self.p._task_lock.locked() else '空闲'}",
            f"认证锁：{'忙碌' if self.p._auth_lock.locked() else '空闲'}",
            f"R18当前上下文：{self.p._current_allow_r18}",
            f"起始页覆盖：{getattr(self.p, '_current_start_page_override', None)}",
            f"搜索深度覆盖：{getattr(self.p, '_current_search_max_depth_override', None)}",
            f"最近收集结束原因：{getattr(self.p, '_last_collect_end_reason', '')}",
            f"下载目录：{self.short_path(c.get('download_dir'))}",
            f"发送模式：{c.get('send_mode')} / forward_mode={c.get('forward_mode')}",
            f"API记录数：{len(self.records)}，输出记录数：{len(self.outputs)}",
        ])


    def files_text(self, limit=10):
        saved = list(getattr(self.p, "_last_saved_files", []) or [])
        label = getattr(self.p, "_last_saved_label", "") or ""
        if not saved:
            return "暂无最近预览图文件记录。请先执行一次 Pixiv 图片命令。"
        lines = [f"最近预览图文件：{label or '未知任务'}，记录数={len(saved)}"]
        for i, rec in enumerate(saved[:max(1, int(limit))], 1):
            path = Path(str(rec.get("path", "")))
            exists = path.exists()
            size = path.stat().st_size if exists else 0
            lines.append(
                f"{i}. exists={exists} size={size}B work_id={rec.get('work_id','')} page={rec.get('page','')} path={self.short_path(path)}"
            )
        if len(saved) > max(1, int(limit)):
            lines.append(f"……还有 {len(saved) - max(1, int(limit))} 条未显示。")
        return "\n".join(lines)

    def clear(self):
        self.records.clear()
        self.outputs.clear()
        self.p._last_api_debug = ""
        self.p._last_debug = ""
        self.p._last_saved_files = []
        self.p._last_saved_label = ""
