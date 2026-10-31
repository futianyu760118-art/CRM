"""回填询价单产品图（历史导入时未提取）。

源文件《销2询价.xlsx》由 WPS 生成，图片放在非标准路径 `xl/drawings/media/`
（标准应为 `xl/media/`），因此需要直接解析 zip + drawing XML。

用法：
    python -m app.db.import_inquiry_images --file "E:/traexm/CRM/销2询价.xlsx"           # dry-run
    python -m app.db.import_inquiry_images --file "..." --apply                        # 写库
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import zipfile
from typing import Any

from sqlalchemy import select

from app.db.import_inquiries import parse_sheet
from app.db.session import async_session_factory, engine
from app.models.business import Inquiry, InquiryItem
from app.services import storage

MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "bmp": "image/bmp"}


def _rels(z: zipfile.ZipFile, path: str) -> dict[str, str]:
    """读取 .rels，返回 {Id: Target}。"""
    try:
        xml = z.read(path).decode("utf-8", "ignore")
    except KeyError:
        return {}
    pairs = re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', xml)
    return dict(pairs)


def _resolve(base_file: str, target: str) -> str:
    """按 base_file 所在目录解析相对 target（xlsx 内部路径）。"""
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = posixpath.dirname(base_file)
    return posixpath.normpath(posixpath.join(base_dir, target))


def _sheet_to_drawing(z: zipfile.ZipFile) -> dict[str, str]:
    """sheet 名 -> drawing xml 路径（按 relationship Type 匹配，不假设 rId）。"""
    wb = z.read("xl/workbook.xml").decode("utf-8", "ignore")
    wb_rels_xml = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "ignore")
    wb_rels = {
        rid: (target, rtype)
        for rid, rtype, target in re.findall(
            r'<Relationship[^>]*Id="([^"]+)"[^>]*Type="([^"]*)"[^>]*Target="([^"]+)"',
            wb_rels_xml,
        )
    }
    # 兼容属性顺序：Id/Type/Target 任意顺序
    if not wb_rels:
        wb_rels = {}
        for m in re.finditer(r"<Relationship([^>]+)/>", wb_rels_xml):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            rid = attrs.get("Id")
            if rid:
                wb_rels[rid] = (attrs.get("Target", ""), attrs.get("Type", ""))

    result: dict[str, str] = {}
    for m in re.finditer(r"<sheet([^>]+)/>", wb):
        attrs = dict(re.findall(r'([\w:]+)="([^"]*)"', m.group(1)))
        name = attrs.get("name")
        rid = attrs.get("r:id") or attrs.get("id")
        if not name or not rid:
            continue
        target, _type = wb_rels.get(rid, ("", ""))
        if not target:
            continue
        sheet_path = _resolve("xl/workbook.xml", target)

        sheet_rels_path = posixpath.join(
            posixpath.dirname(sheet_path), "_rels", posixpath.basename(sheet_path) + ".rels"
        )
        if sheet_rels_path not in z.namelist():
            continue
        sheet_rels_xml = z.read(sheet_rels_path).decode("utf-8", "ignore")
        for rel in re.finditer(r"<Relationship([^>]+)/>", sheet_rels_xml):
            rattrs = dict(re.findall(r'([\w:]+)="([^"]*)"', rel.group(1)))
            rtype = rattrs.get("Type", "")
            rtarget = rattrs.get("Target", "")
            if rtype.endswith("/drawing") and rtarget:
                result[name] = _resolve(sheet_path, rtarget)
                break
    return result


def extract_images(path: str) -> dict[str, list[tuple[int, bytes, str]]]:
    """返回 {sheet 名: [(锚点行(0 基), 图片字节, 文件名)]}。"""
    z = zipfile.ZipFile(path)
    mapping = _sheet_to_drawing(z)
    out: dict[str, list[tuple[int, bytes, str]]] = {}

    for sheet, drawing_path in mapping.items():
        base = drawing_path.rsplit("/", 1)[-1]
        draw_rels = _rels(z, f"xl/drawings/_rels/{base}.rels")
        drawing_dir = drawing_path.rsplit("/", 1)[0]
        try:
            xml = z.read(drawing_path).decode("utf-8", "ignore")
        except KeyError:
            continue

        entries: list[tuple[int, bytes, str]] = []
        # 每个锚点块：<xdr:from>...<xdr:row>N</xdr:row> ... <a:blip r:embed="rIdX"
        for anchor in re.finditer(
            r"<xdr:(?:twoCellAnchor|oneCellAnchor)[^>]*>(.*?)</xdr:(?:twoCellAnchor|oneCellAnchor)>", xml, re.S
        ):
            block = anchor.group(1)
            row_match = re.search(r"<xdr:row>(\d+)</xdr:row>", block)
            embed_match = re.search(r'<a:blip[^>]*r:embed="([^"]+)"', block)
            if not row_match or not embed_match:
                continue
            target = draw_rels.get(embed_match.group(1))
            if not target:
                continue
            media_path = f"{drawing_dir}/{target.lstrip('/')}"
            media_path = media_path.replace("/./", "/")
            if media_path not in z.namelist():
                # 兜底：尝试标准 xl/media/
                alt = "xl/" + target.lstrip("/").replace("xl/", "")
                media_path = alt if alt in z.namelist() else media_path
            if media_path not in z.namelist():
                continue
            data = z.read(media_path)
            filename = media_path.rsplit("/", 1)[-1]
            entries.append((int(row_match.group(1)), data, filename))
        if entries:
            out[sheet] = entries
    return out


def match_images(items: list[dict[str, Any]], images: list[tuple[int, bytes, str]]) -> dict[int, tuple[bytes, str]]:
    """把图片按锚点行匹配到明细行：取「明细行 < 锚点行」 中最大的那个明细。"""
    matched: dict[int, tuple[bytes, str]] = {}
    rows = sorted((i["_row"], i["_sort"]) for i in items)
    if not rows:
        return matched
    for row, data, filename in images:
        best: int | None = None
        for item_row, sort in rows:
            if item_row < row:
                best = sort
            else:
                break
        if best is None:
            # 图片在第一条明细之前，视为抬头图，忽略
            continue
        matched.setdefault(best, (data, filename))
    return matched


async def run(path: str, apply: bool) -> None:
    print("[images] 解析图片锚点…")
    images_by_sheet = extract_images(path)
    total_images = sum(len(v) for v in images_by_sheet.values())
    print(f"[images] 含图片页签 {len(images_by_sheet)} 个，图片 {total_images} 张")

    # 重新解析页签，得到 sheet -> inquiry_no / 明细顺序
    from python_calamine import CalamineWorkbook

    wb = CalamineWorkbook.from_path(path)
    sheet_to_no: dict[str, str] = {}
    parsed_items: dict[str, list[dict[str, Any]]] = {}
    for name in wb.sheet_names:
        if name not in images_by_sheet:
            continue
        try:
            rows = wb.get_sheet_by_name(name).to_python()
        except Exception:  # noqa: BLE001
            continue
        head, items, _spec_rows = parse_sheet(rows)
        no = str(head.get("inquiry_no") or "").strip()
        if not no:
            continue
        sheet_to_no[name] = no
        parsed_items[no] = items

    stats = {"inquiry": 0, "image": 0, "skip": 0, "nomatch": 0}
    async with async_session_factory() as db:
        inquiries = (await db.execute(select(Inquiry).where(Inquiry.source == "IMPORT"))).scalars().all()
        by_no = {i.inquiry_no: i for i in inquiries}

        for sheet, entries in images_by_sheet.items():
            inquiry_no = sheet_to_no.get(sheet)
            if not inquiry_no:
                stats["skip"] += 1
                continue
            inquiry = by_no.get(inquiry_no)
            if inquiry is None:
                stats["skip"] += 1
                continue

            rows_for_match = []
            for idx, item in enumerate(parsed_items.get(inquiry_no, []), start=1):
                item["_sort"] = idx
                rows_for_match.append(item)
            if not rows_for_match:
                stats["skip"] += 1
                continue

            matched = match_images(rows_for_match, entries)
            if not matched:
                stats["nomatch"] += 1
                continue

            db_items = (
                (await db.execute(select(InquiryItem).where(InquiryItem.inquiry_id == inquiry.id))).scalars().all()
            )
            by_sort = {i.sort: i for i in db_items}
            changed = 0
            for sort, (data, filename) in matched.items():
                target = by_sort.get(sort)
                if target is None or target.image_file_id:
                    continue
                ext = filename.rsplit(".", 1)[-1].lower()
                record = await storage.save_bytes(
                    db,
                    filename=f"{inquiry_no}-{sort}-{filename}",
                    data=data,
                    mime=MIME_BY_EXT.get(ext, "image/png"),
                    module="inquiry",
                    biz_id=inquiry.id,
                )
                target.image_file_id = record.id
                changed += 1
                stats["image"] += 1
            if changed:
                stats["inquiry"] += 1

        if apply:
            await db.commit()
        else:
            await db.rollback()

    mode = "APPLY（已写库）" if apply else "DRY-RUN（未写库）"
    print(f"[images] 模式：{mode}")
    print(
        f"[images] 命中询价单 {stats['inquiry']}，写入图片 {stats['image']}，"
        f"跳过 {stats['skip']}，无匹配 {stats['nomatch']}"
    )
    if not apply:
        print("[images] 加 --apply 执行写入")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import asyncio

    asyncio.run(run(args.file, args.apply))


if __name__ == "__main__":
    main()
    sys.exit(0)
