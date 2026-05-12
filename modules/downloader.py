import asyncio
import secrets
import string
import time
import zipfile
from pathlib import Path
import aiohttp
from astrbot.api import logger
try:
    import pyzipper
except ImportError:
    pyzipper = None
from .base import BaseService
from .pixiv_utils import (
    build_illust_info, build_novel_info, extract_items, fmt_time, full_command_args,
    getv, is_ai, is_r18, item_id, novel_cover_url, parse_count_arg, pick_image_url,
    read_json, safe_filename, searchable_text, split_terms, stat_value, tags_text,
    to_int, unique_items, user_info, write_json,
)

class DownloaderService(BaseService):
    def convert_image_proxy_url(self, url: str, proxy=None) -> str:
        c = self.config_service.cfg()
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
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    if chunk:
                        f.write(chunk)

    def generate_zip_password(self, length=64) -> str:
        """生成 ZIP 加密密码。

        默认长度 64。字符类型包含小写字母、大写字母、数字和特殊符号。
        四类字符占比以 25% 为均值做正态分布随机波动，避免每次比例完全固定。
        """
        length = max(8, min(int(length or 64), 64))
        lowers = string.ascii_lowercase
        uppers = string.ascii_uppercase
        digits = string.digits
        symbols = "!@#$%^&*()-_=+[]{};,.?"
        groups = [lowers, uppers, digits, symbols]

        rng = secrets.SystemRandom()
        mean = length / len(groups)
        sigma = max(1.0, length * 0.06)
        min_count = 1
        max_count = max(min_count, int(length * 0.45))

        counts = [
            max(min_count, min(max_count, int(round(rng.gauss(mean, sigma)))))
            for _ in groups
        ]

        # 调整总数到 length，同时尽量保留正态分布生成的波动。
        while sum(counts) < length:
            counts[rng.randrange(len(counts))] += 1
        while sum(counts) > length:
            candidates = [i for i, c in enumerate(counts) if c > min_count]
            if not candidates:
                break
            counts[rng.choice(candidates)] -= 1

        chars = []
        for pool, count in zip(groups, counts):
            chars.extend(rng.choice(pool) for _ in range(count))
        rng.shuffle(chars)
        return "".join(chars)

    def new_zip_writer(self, zip_path: Path):
        if not self.config_service.cfg().get("encrypt_zip_enabled", bool(self.config.get("encrypt_zip_enabled", False))):
            return zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED), ""
        if pyzipper is None:
            raise RuntimeError("已开启 ZIP 加密，但缺少依赖 pyzipper，请安装 requirements.txt 后重启插件。")
        password = self.generate_zip_password(self.config_service.cfg().get("zip_password_length", 64))
        zf = pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES)
        zf.setpassword(password.encode("utf-8"))
        return zf, password

    def remember_zip_password(self, password: str):
        self._last_zip_password = password or ""

    def peek_zip_password(self) -> str:
        return getattr(self, "_last_zip_password", "") or ""

    def pop_zip_password(self) -> str:
        password = getattr(self, "_last_zip_password", "") or ""
        self._last_zip_password = ""
        return password

    def write_zip_archive(self, zip_path: Path, info_path: Path, files, include_info_txt: bool):
        zf, zip_password = self.new_zip_writer(zip_path)
        with zf:
            if include_info_txt:
                zf.write(info_path, "info.txt")
            for p, arcname in files:
                zf.write(p, arcname)
        return zip_password

    async def prepare_illust_files(self, items, label="pixivs", progress_cb=None, make_zip=True):
        c = self.config_service.cfg()
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
                    saved.append(row)

        info_seen_ids = set()
        for _, item, _, total in saved:
            iid = item_id(item)
            info_key = iid or id(item)
            if info_key in info_seen_ids:
                continue
            info_seen_ids.add(info_key)
            infos.append(build_illust_info(item, None, total, c["image_quality"], c["include_tags"], c["max_tags_display"], c["include_caption"]))
        info_path = base / "info.txt"
        info_path.write_text("\n\n".join(infos), encoding="utf-8")
        zip_path = c["download_dir"] / f"{safe_filename(label, 40)}_{ts}.zip"
        if not make_zip:
            return base, zip_path, saved
        zip_seen_ids = set()
        zip_ids = []
        for _, item, _, _ in saved:
            iid = item_id(item)
            if iid and iid not in zip_seen_ids:
                zip_seen_ids.add(iid)
                zip_ids.append(iid)
        zip_total = max(1, len(zip_ids))
        zip_done_ids = set()
        zip_files = []
        for p, item, *_ in saved:
            iid = item_id(item)
            if progress_cb and iid and iid not in zip_done_ids:
                zip_done_ids.add(iid)
                await progress_cb(iid, len(zip_done_ids), zip_total)
            zip_files.append((p, f"images/{p.name}"))
        zip_password = await asyncio.to_thread(
            self.write_zip_archive, zip_path, info_path, zip_files, c["include_info_txt"]
        )
        self.remember_zip_password(zip_password)
        return base, zip_path, saved

    async def prepare_original_zip_from_items(self, items, label="pixivc_original", progress_cb=None):
        old_quality = self.config.get("image_quality")
        self.config["image_quality"] = "original"
        try:
            return await self.prepare_illust_files(items, label, progress_cb=progress_cb)
        finally:
            if old_quality is None:
                self.config.pop("image_quality", None)
            else:
                self.config["image_quality"] = old_quality

    async def prepare_novel_files(self, items, label="pixivc_novel", progress_cb=None):
        c = self.config_service.cfg()
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
                text = await self.novel.fetch_novel_text(nid)
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
        zip_seen_ids = set()
        zip_ids = []
        for _, item, _ in files:
            nid = item_id(item)
            if nid and nid not in zip_seen_ids:
                zip_seen_ids.add(nid)
                zip_ids.append(nid)
        zip_total = max(1, len(zip_ids))
        zip_done_ids = set()
        zip_files = []
        for p, item, text in files:
            nid = item_id(item)
            if progress_cb and nid and nid not in zip_done_ids:
                zip_done_ids.add(nid)
                await progress_cb(nid, len(zip_done_ids), zip_total)
            sub = "covers" if "cover" in p.name else "novels"
            zip_files.append((p, f"{sub}/{p.name}"))
        zip_password = await asyncio.to_thread(
            self.write_zip_archive, zip_path, info_path, zip_files, c["include_info_txt"]
        )
        self.remember_zip_password(zip_password)
        return base, zip_path, files, infos

    async def yield_pack_progress(self, event, items, kind="作品"):
        ids = []
        seen = set()
        for item in items:
            iid = item_id(item)
            if not iid or iid in seen:
                continue
            seen.add(iid)
            ids.append(iid)
        total = max(1, len(ids))
        for idx, iid in enumerate(ids, 1):
            percent = int(idx * 100 / total)
            yield event.plain_result(f"正在处理{kind}ID：{iid}（{idx}/{total}，{percent}%）")
            await asyncio.sleep(0)

    async def prepare_with_live_progress(self, event, items, kind, prepare_factory):
        ids = []
        id_set = set()
        for item in items:
            iid = item_id(item)
            if iid and iid not in id_set:
                id_set.add(iid)
                ids.append(iid)
        total = max(1, len(ids))
        seen = set()
        queue = asyncio.Queue()

        async def progress_cb(iid, idx=None, total_count=None):
            if not self.config_service.cfg().get("show_pack_progress", True):
                return
            iid = str(iid or "").strip()
            if not iid or iid in seen:
                return
            seen.add(iid)
            idx = int(idx or len(seen))
            total_count = max(1, int(total_count or total))
            percent = int(idx * 100 / total_count)
            yield_kind = "作品" if kind in {"作品", "画作"} else kind
            await queue.put(f"正在打包，{yield_kind}ID：{iid}，当前进度({idx}/{total_count}){percent}%。")

        task = asyncio.create_task(prepare_factory(progress_cb))
        while True:
            if task.done() and queue.empty():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.2)
                yield ("progress", event.plain_result(msg))
            except asyncio.TimeoutError:
                pass
        yield ("result", await task)
