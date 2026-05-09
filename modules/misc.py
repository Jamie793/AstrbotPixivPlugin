import asyncio
from .base import BaseService
from .help import build_help_text as build_pixivc_help_text


class MiscService(BaseService):
    def admin_mark(self, key: str) -> str:
        return " [Admin]" if self.config_service.cfg().get(key, True) else ""

    def build_help_text(self) -> str:
        return build_pixivc_help_text(self.admin_mark)

    async def pixiv_autocomplete(self, word: str):
        api = await self.auth.api()
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
            resp = await self.auth.api_no_auth_requests_call("GET", url, params=params)
            status = getattr(resp, "status_code", 0)
            if status == 404:
                last_error = f"HTTP 404: {url}"
                continue
            if self.auth._looks_auth_failed(resp=resp):
                raise RuntimeError(getattr(resp, "text", "")[:300])
            if status >= 400:
                raise RuntimeError(getattr(resp, "text", "")[:300])
            api = await self.auth.api()
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
