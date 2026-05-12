import asyncio
import base64
import shutil
from pathlib import Path
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, File, Image, Node, Nodes, Plain
from .base import BaseService
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)

class SenderService(BaseService):
    def platform_id(self, event) -> str:
        for name in ("get_platform_id", "get_platform_name"):
            try:
                fn = getattr(event, name, None)
                if callable(fn):
                    value = str(fn() or "").strip().lower()
                    if value:
                        return value
            except Exception:
                pass
        try:
            meta = getattr(event, "platform_meta", None)
            value = str(getattr(meta, "id", "") or getattr(meta, "name", "") or "").strip().lower()
            if value:
                return value
        except Exception:
            pass
        return ""

    def is_telegram(self, event) -> bool:
        platform = self.platform_id(event)
        return platform in {"telegram", "tg"} or "telegram" in platform

    async def send_zip(self, event: AstrMessageEvent, zip_path: Path, suppress_ready: bool = False, password: str = ""):
        c = self.config_service.cfg()
        size = zip_path.stat().st_size
        size_text = self.cache.format_size(size)
        if size > c["max_zip_mb"] * 1024 * 1024:
            yield event.plain_result(f"ZIP 大小 {size_text}，超过限制 {c['max_zip_mb']}MB，已取消发送。")
            return
        password = password or self.downloader.pop_zip_password()
        if not suppress_ready:
            if password:
                yield event.plain_result(f"ZIP 已生成：{zip_path.name}，大小 {size_text}，已加密。解压密码：【{password}】。正在发送文件……")
            else:
                yield event.plain_result(f"ZIP 已生成：{zip_path.name}，大小 {size_text}，正在发送文件……")
        elif password:
            yield event.plain_result(f"缓存 ZIP 已加密。解压密码：【{password}】")
        try:
            # 优先使用本地文件路径发送，部分适配器对 base64 文件消息支持不稳定。
            yield event.chain_result([File(name=zip_path.name, file=str(zip_path))])
            yield event.plain_result("ZIP 文件发送请求已提交。若聊天窗口未显示文件，请检查当前适配器是否支持本地路径文件消息。")
            return
        except Exception as e1:
            logger.warning(f"pixivc zip send by path failed: {e1}", exc_info=True)
            try:
                data = base64.b64encode(zip_path.read_bytes()).decode()
                yield event.chain_result([File(name=zip_path.name, file="base64://" + data)])
                yield event.plain_result("ZIP 文件发送请求已提交（base64 兜底）。若聊天窗口未显示文件，请检查当前适配器文件消息支持。")
                return
            except Exception as e2:
                yield event.plain_result(f"ZIP 文件发送失败：本地路径发送失败：{e1}；base64 发送失败：{e2}")

    async def send_images(self, event, saved):
        c = self.config_service.cfg()
        for p, item, idx, total in saved:
            comps = [Image.fromFileSystem(str(p))]
            if c["include_work_info"]:
                comps.append(Plain(build_illust_info(item, idx, total, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"])))
            yield event.chain_result(comps)
            await asyncio.sleep(0.2)

    async def send_forward(self, event, saved, novel_infos=None):
        c = self.config_service.cfg()
        batch_size = 20

        # Telegram 没有 QQ/OneBot 的合并转发 Nodes，直接降级为普通消息。
        if self.is_telegram(event):
            if novel_infos is not None:
                all_infos = list(novel_infos or [])
                total = len(all_infos)
                if not all_infos:
                    return
                for idx, info in enumerate(all_infos, 1):
                    prefix = f"Pixivc 小说预览 {idx}/{total}\n" if total > 1 else "Pixivc 小说预览\n"
                    text = prefix + str(info or "")
                    # Telegram 单条文本有长度限制，保守截断，避免适配器发送失败。
                    yield event.plain_result(text[:3500])
                    await asyncio.sleep(0.2)
                return
            async for r in self.send_images(event, saved):
                yield r
            return

        if novel_infos is not None:
            all_infos = list(novel_infos or [])
            total = len(all_infos)
            if not all_infos:
                return
            for start in range(0, total, batch_size):
                part = all_infos[start:start + batch_size]
                nodes = [Node(name="PixivcNovel", uin="0", content=[Plain(info)]) for info in part]
                if total > batch_size:
                    yield event.plain_result(f"正在发送小说合并转发预览：{start + 1}-{start + len(part)}/{total}")
                yield event.chain_result([Nodes(nodes)])
                await asyncio.sleep(0.2)
            return

        all_saved = list(saved or [])
        total = len(all_saved)
        if not all_saved:
            return
        for start in range(0, total, batch_size):
            part = all_saved[start:start + batch_size]
            nodes = []
            for p, item, idx, total_pages in part:
                content = [Image.fromFileSystem(str(p))]
                if c["forward_mode"] != "only_images":
                    content.append(Plain(build_illust_info(item, idx, total_pages, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"])))
                nodes.append(Node(name="Pixivc", uin="0", content=content))
            if total > batch_size:
                yield event.plain_result(f"正在发送图片合并转发预览：{start + 1}-{start + len(part)}/{total}")
            yield event.chain_result([Nodes(nodes)])
            await asyncio.sleep(0.2)

    def _plain_item(self, item):
        if isinstance(item, dict):
            return item
        try:
            if hasattr(item, "__dict__"):
                return item.__dict__
        except Exception:
            pass
        return item

    async def dispatch_illust_result(self, event, base, zip_path, saved):
        c = self.config_service.cfg()
        # 图片搜索默认只发送预览，不自动生成/发送 ZIP。Telegram 不支持 QQ 合并转发，直接普通图片发送。
        preview_saved = saved
        if self.is_telegram(event):
            self.debug.record_output("Telegram 平台：跳过合并转发，改用普通图片预览发送。")
            async for r in self.send_images(event, preview_saved):
                yield r
            if c["clean_after_send"]:
                shutil.rmtree(base, ignore_errors=True)
            return
        try:
            sent_any = False
            async for r in self.send_forward(event, preview_saved):
                sent_any = True
                self.debug.record_output("合并转发预览消息已提交。")
                yield r
            if not sent_any:
                msg = "合并转发预览没有生成任何消息，已改用普通图片发送兜底。"
                self.debug.record_output(msg)
                yield event.plain_result(msg)
                async for r in self.send_images(event, preview_saved):
                    yield r
        except Exception as e:
            msg = f"合并转发预览发送失败，已改用普通图片发送兜底：{type(e).__name__}: {e}"
            logger.warning(msg, exc_info=True)
            self.debug.record_output(msg, kind="error")
            yield event.plain_result(msg)
            async for r in self.send_images(event, preview_saved):
                yield r
        if c["clean_after_send"]:
            shutil.rmtree(base, ignore_errors=True)

    async def dispatch_novel_result(self, event, base, zip_path, files, infos):
        c = self.config_service.cfg()
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

    async def build_novel_preview_infos(self, items):
        c = self.config_service.cfg()
        infos = []
        total = max(1, len(items))
        used_preview_chars = 0
        total_budget = c["novel_preview_total_chars"]
        skip_msg = "\n\n正文预览：为避免内容过长，后续作品不展示正文预览。"
        for item in items:
            info = build_novel_info(item, c["include_tags"], c["max_tags_display"], c["include_caption"])
            nid = item_id(item)
            if used_preview_chars >= total_budget:
                info += skip_msg
                infos.append(info)
                continue
            text = ""
            if nid:
                try:
                    text = await self.novel.fetch_novel_text(nid)
                except Exception as e:
                    logger.warning(f"pixivc novel preview text failed {nid}: {e}")
                    text = ""
            if text:
                if total == 1:
                    dynamic_len = len(text)
                else:
                    dynamic_len = max(1, len(text) // (total + 1))
                remaining_budget = max(0, total_budget - used_preview_chars)
                preview_len = min(dynamic_len, c["novel_preview_max_chars"], remaining_budget)
                if preview_len > 0:
                    preview = text[:preview_len]
                    used_preview_chars += len(preview)
                    more = "\n……" if len(text) > preview_len else ""
                    info += f"\n\n正文预览：\n{preview}{more}"
                else:
                    info += skip_msg
            else:
                info += "\n\n正文预览：获取失败或为空"
            infos.append(info)
        return infos
