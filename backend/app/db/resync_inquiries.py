"""存量询价单补数据：客户标准纵向块（spec_rows）+ 缺失的明细字段。

首轮导入只解析了横向明细表，纵向「客户标准」块（产品尺寸 / 显色指数 / 灯珠数量 /
功能 / 电线插头 / 认证 / 报价提供时间 / 其他要求 / 需求数量 …）被漏掉；
本脚本按源文件回填到已导入的询价单，并为「只有纵向块」的页签补建明细。

用法：
    python -m app.db.resync_inquiries --file "E:/traexm/CRM/销2询价.xlsx"           # dry-run
    python -m app.db.resync_inquiries --file "..." --apply                        # 写库
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from python_calamine import CalamineWorkbook
from sqlalchemy import select

from app.db.import_inquiries import (
    FOB_LABEL,
    SKIP_SHEETS,
    parse_sheet,
    standard_text,
)
from app.db.session import async_session_factory, engine
from app.models.business import Inquiry, InquiryItem

# 需要从纵向块回填到明细的字段
FILL_FIELDS = (
    "power",
    "voltage",
    "color_temp",
    "lumen",
    "light_source",
    "size",
    "cri",
    "led_count",
    "feature",
    "plug",
    "main_body",
    "lamp_shade",
    "reflector",
    "waterproof",
    "certification",
    "quote_lead_time",
)


def collect(path: str) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
    """返回 {询价单号: (head, items)}，并附带 spec_rows。"""
    wb = CalamineWorkbook.from_path(path)
    result: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for name in wb.sheet_names:
        if name in SKIP_SHEETS:
            continue
        try:
            rows = wb.get_sheet_by_name(name).to_python()
        except Exception:  # noqa: BLE001
            continue
        head, items, spec_rows = parse_sheet(rows)
        no = str(head.get("inquiry_no") or "").strip()
        if not no:
            continue
        head["_spec_rows"] = spec_rows
        result[no] = (head, items)
    return result


async def run(path: str, apply: bool) -> None:
    parsed = collect(path)
    print(f"[resync] 源文件解析出 {len(parsed)} 张询价单")

    stats = {
        "inquiry": 0,
        "spec": 0,
        "item_update": 0,
        "item_create": 0,
        "missing": 0,
    }

    async with async_session_factory() as db:
        inquiries = (await db.execute(select(Inquiry).where(Inquiry.source == "IMPORT"))).scalars().all()
        by_no = {i.inquiry_no: i for i in inquiries}

        for no, (head, items) in parsed.items():
            inquiry = by_no.get(no)
            if inquiry is None:
                stats["missing"] += 1
                continue

            spec_rows = head.get("_spec_rows") or []
            changed = False

            if spec_rows and not inquiry.spec_rows:
                inquiry.spec_rows = spec_rows
                stats["spec"] += 1
                changed = True

            other = standard_text(spec_rows, "其他要求")
            if other and not inquiry.requirement_text:
                inquiry.requirement_text = other
                changed = True
            if standard_text(spec_rows, FOB_LABEL) is not None and not inquiry.trade_terms:
                inquiry.trade_terms = FOB_LABEL
                changed = True
            if head.get("version_no") and not inquiry.version_no:
                inquiry.version_no = str(head["version_no"])
                changed = True
            if head.get("department_name_text") and not inquiry.department_name_text:
                inquiry.department_name_text = str(head["department_name_text"])
                changed = True
            if head.get("owner_name_text") and not inquiry.owner_name_text:
                inquiry.owner_name_text = str(head["owner_name_text"])
                changed = True
            if head.get("market") and not inquiry.market:
                inquiry.market = str(head["market"])
                changed = True

            existing = list(
                (
                    await db.execute(
                        select(InquiryItem)
                        .where(InquiryItem.inquiry_id == inquiry.id)
                        .order_by(InquiryItem.sort, InquiryItem.created_at)
                    )
                )
                .scalars()
                .all()
            )

            if not existing and items:
                for idx, item in enumerate(items, start=1):
                    payload = dict(item)
                    payload.pop("_row", None)
                    payload["sort"] = idx
                    db.add(InquiryItem(inquiry_id=inquiry.id, **payload))
                    stats["item_create"] += 1
                changed = True
            else:
                for idx, row in enumerate(existing):
                    if idx >= len(items):
                        break
                    source = items[idx]
                    for field in FILL_FIELDS:
                        value = source.get(field)
                        if value and not getattr(row, field, None):
                            setattr(row, field, value)
                            stats["item_update"] += 1
                    qty = source.get("quantity")
                    if qty and (not row.quantity or float(row.quantity) == 0):
                        row.quantity = qty
                        stats["item_update"] += 1
                    changed = True

            if changed:
                stats["inquiry"] += 1

        if apply:
            await db.commit()
        else:
            await db.rollback()

    mode = "APPLY（已写库）" if apply else "DRY-RUN（未写库）"
    print(f"[resync] 模式：{mode}")
    print(
        f"[resync] 命中询价单 {stats['inquiry']}，补纵向块 {stats['spec']}，"
        f"更新明细字段 {stats['item_update']}，补建明细 {stats['item_create']}，"
        f"源文件有但库中无 {stats['missing']}"
    )
    if not apply:
        print("[resync] 加 --apply 执行写入")
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
