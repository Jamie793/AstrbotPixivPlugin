import html
import json
import re
from pathlib import Path
from typing import Any, Iterable

from astrbot.api.event import AstrMessageEvent

def read_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def safe_filename(name: str, max_len: int = 80) -> str:
    name = html.unescape(str(name or ""))
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", name)
    name = name.strip(" ._") or "untitled"
    return name[:max_len]

def getv(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def to_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default

def split_terms(text: str):
    return [x.strip() for x in re.split(r"[,，]", text or "") if x.strip()]

def parse_count_arg(text: str, default_count: int, max_count: int):
    text = (text or "").strip()
    count = max(1, min(default_count, max_count))
    # 只支持 n3 这种数量格式，可放在参数任意位置。
    # 纯数字不再作为数量解析，避免和关键词、ID、页码混淆。
    m = re.search(r"(?:^|\s)n(\d+)(?=\s|$)", text, flags=re.IGNORECASE)
    if m:
        count = max(1, min(int(m.group(1)), max_count))
        text = (text[:m.start()] + " " + text[m.end():]).strip()
    return text, count

def full_command_args(event: AstrMessageEvent, command_name: str, injected: str = "") -> str:
    """优先从完整 message_str 提取命令后的全部参数，避免 AstrBot 参数注入只取首段。"""
    text = (getattr(event, "message_str", "") or "").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    if text == command_name:
        return ""
    prefix = command_name + " "
    if text.startswith(prefix):
        return text[len(prefix):].strip()
    return (injected or "").strip()

def tags_text(item) -> list[str]:
    tags = []
    for tag in getv(item, "tags", []) or []:
        name = getv(tag, "name", "")
        trans = getv(tag, "translated_name", "")
        if name:
            tags.append(str(name))
        if trans:
            tags.append(str(trans))
    return tags

def searchable_text(item) -> str:
    parts = [getv(item, "title", ""), getv(item, "caption", ""), getv(item, "user", {}) and getv(getv(item, "user", {}), "name", "")]
    parts.extend(tags_text(item))
    return " ".join(str(x or "") for x in parts).lower()

def is_r18(item) -> bool:
    return to_int(getv(item, "x_restrict", 0), 0) != 0

def is_ai(item) -> bool:
    return to_int(getv(item, "illust_ai_type", getv(item, "ai_type", 0)), 0) == 2

def stat_value(item, *keys):
    for k in keys:
        v = getv(item, k, None)
        if v is not None:
            return to_int(v, 0)
    return 0

def item_id(item):
    return str(getv(item, "id", ""))

def unique_items(items: Iterable[Any]):
    seen = set()
    out = []
    for item in items:
        iid = item_id(item)
        if iid and iid not in seen:
            seen.add(iid)
            out.append(item)
    return out

def extract_items(resp, kind="illust"):
    if not resp:
        return []
    keys = ["illusts", "ranking_illusts", "novels", "ranking_novels"] if kind == "illust" else ["novels", "ranking_novels"]
    for key in keys:
        value = getv(resp, key, None)
        if value:
            return list(value)
    return []

def pick_image_url(item, quality: str):
    urls = []
    meta_pages = getv(item, "meta_pages", None) or []
    if meta_pages:
        for page in meta_pages:
            urls.append(getv(page, "image_urls", {}) or {})
    else:
        image_urls = dict(getv(item, "image_urls", {}) or {})
        meta_single = getv(item, "meta_single_page", {}) or {}
        original = getv(meta_single, "original_image_url", None)
        if original:
            image_urls["original"] = original
        urls.append(image_urls)

    order = {
        "original": ["original", "large", "medium", "square_medium"],
        "large": ["large", "original", "medium", "square_medium"],
        "medium": ["medium", "large", "original", "square_medium"],
    }.get(quality, ["large", "original", "medium", "square_medium"])
    result = []
    for u in urls:
        for key in order:
            if isinstance(u, dict) and u.get(key):
                result.append(u[key])
                break
    return result

def novel_cover_url(item):
    image_urls = getv(item, "image_urls", {}) or {}
    if isinstance(image_urls, dict):
        return image_urls.get("large") or image_urls.get("medium") or image_urls.get("square_medium") or ""
    return ""

def fmt_time(value):
    return str(value or "未知")

def user_info(item):
    user = getv(item, "user", {}) or {}
    return str(getv(user, "name", "未知")), str(getv(user, "id", "未知"))

def build_illust_info(item, page=None, page_total=None, quality="large", include_tags=True, max_tags=20, include_caption=True):
    author, author_id = user_info(item)
    iid = item_id(item)
    tags = tags_text(item)
    lines = [
        f"标题：{getv(item, 'title', '未知')}",
        f"作者：{author}",
        f"作者ID：{author_id}",
        f"作品ID：{iid}",
        f"发布时间：{fmt_time(getv(item, 'create_date', ''))}",
        f"类型：{getv(item, 'type', 'illust')}",
        f"图片质量：{quality}",
        f"链接：https://www.pixiv.net/artworks/{iid}",
    ]
    if include_tags and tags:
        lines.append("标签：" + "、".join(tags[:max_tags]))
    if include_caption and getv(item, "caption", ""):
        cap = re.sub(r"<[^>]+>", "", str(getv(item, "caption", "")))
        lines.append("简介：" + html.unescape(cap)[:500])
    return "\n".join(lines)

def build_novel_info(item, include_tags=True, max_tags=20, include_caption=True):
    author, author_id = user_info(item)
    nid = item_id(item)
    series = getv(item, "series", {}) or {}
    tags = tags_text(item)
    lines = [
        f"小说标题：{getv(item, 'title', '未知')}",
        f"作者：{author}",
        f"作者ID：{author_id}",
        f"小说ID：{nid}",
        f"发布时间：{fmt_time(getv(item, 'create_date', ''))}",
        f"更新时间：{fmt_time(getv(item, 'update_date', ''))}",
        f"字数：{stat_value(item, 'text_length')}",
        f"系列ID：{getv(series, 'id', '无')}",
        f"系列标题：{getv(series, 'title', '无')}",
        f"第几话：{getv(series, 'order', '未知')}",
        f"浏览：{stat_value(item, 'total_view', 'total_views')}",
        f"收藏：{stat_value(item, 'total_bookmarks')}",
        f"评论：{stat_value(item, 'total_comments', 'comment_count', 'commentCount')}",
        f"R18：{'是' if is_r18(item) else '否'}",
        f"AI：{'是' if is_ai(item) else '否'}",
        f"链接：https://www.pixiv.net/novel/show.php?id={nid}",
    ]
    if include_tags and tags:
        lines.append("标签：" + "、".join(tags[:max_tags]))
    if include_caption and getv(item, "caption", ""):
        cap = re.sub(r"<[^>]+>", "", str(getv(item, "caption", "")))
        lines.append("简介：" + html.unescape(cap)[:1000])
    return "\n".join(lines)
