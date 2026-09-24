"""历史询价单导入：《销2询价.xlsx》一个页签 = 一张询价单。

用法：
    python -m app.db.import_inquiries --file "E:/traexm/CRM/销2询价.xlsx"            # dry-run
    python -m app.db.import_inquiries --file "E:/traexm/CRM/销2询价.xlsx" --apply    # 写库
    python -m app.db.import_inquiries --file "..." --limit 5 --verbose              # 仅前 5 张并打印明细

解析规则（按列标题定位，容忍列顺序差异）：
    单据头：含“询价单号”的行 → 下一行取值
    明细：  含“产品型号”和“功率”的行为表头，其后到下一个表头/空行为明细
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from python_calamine import CalamineWorkbook
from sqlalchemy import select

from app.db.session import async_session_factory, engine
from app.models.business import BusinessCode, Company, Inquiry, InquiryItem
from app.models.user import User
from app.services import company_code

SKIP_SHEETS = {"总表", "模板", "模板（25版）"}

HEAD_ALIASES = {
    "名称": "name",
    "部门": "department_name_text",
    "业务员": "owner_name_text",
    "客户编号": "customer_code",
    "客户名": "customer_name",
    "新/老客户": "customer_type",
    "询价单号": "inquiry_no",
    "发起时间": "start_date",
    "结束时间": "end_date",
    "样品可供时间": "sample_date",
    "样品可提供时间": "sample_date",
    "下单时间": "order_date",
    "出货时间": "shipment_date",
    "首单货值（万）": "first_order_amount",
    "首单货值(万)": "first_order_amount",
    "数量（个)": "quantity_total",
    "数量(个)": "quantity_total",
    "年金额": "annual_amount",
    "市场": "market",
    "交样周期": "sample_lead_time",
}

ITEM_ALIASES = {
    "序号": "sort",
    "产品图": "_picture",
    "产品型号": "product_model",
    "产品名称": "product_name",
    "功率": "power",
    "输入电压": "voltage",
    "电池": "battery",
    "色温": "color_temp",
    "光通量/光效": "lumen",
    "光源": "light_source",
    "主体": "main_body",
    "压框": "frame",
    "灯罩": "lamp_shade",
    "反光罩": "reflector",
    "电缆线": "cable",
    "开关": "switch",
    "USB": "usb",
    "防水等级": "waterproof",
    "感应器": "sensor",
    "认证要求": "certification",
    "报价": "quote_price",
    "目标价": "target_price",
    "需求数量": "quantity",
    "报价需时间": "quote_lead_time",
    "其他要求": "other_requirement",
    "其他要求1": "other_requirement",
    "其他要求2": "other_requirement2",
}

DATE_FIELDS = {"start_date", "end_date", "sample_date", "order_date", "shipment_date"}
NUM_FIELDS = {
    "first_order_amount",
    "quantity_total",
    "annual_amount",
    "target_price",
    "quote_price",
    "quantity",
    "sort",
}
EXCEL_EPOCH = dt.datetime(1899, 12, 30)


def norm(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return "" if text.lower() in {"none", "nan"} else text


def as_date(value: object) -> dt.datetime | None:
    parsed: dt.datetime | None = None
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time())
    else:
        text = norm(value)
        if not text:
            return None
        if text.replace(".", "", 1).isdigit():
            parsed = EXCEL_EPOCH + dt.timedelta(days=float(text))
        else:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
                try:
                    parsed = dt.datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
    if parsed is None:
        return None
    # Excel 空单元格常被读成 1900-01-01，视为无效
    if parsed.year < 1990 or parsed.year > 2100:
        return None
    return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed


def as_number(value: object) -> float | None:
    text = norm(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_placeholder(text: str) -> bool:
    return text.strip().lower() in {"", "xxx", "/", "-", "无", "none"}


def clean_code(value: str) -> str:
    """客户编号：Excel 数字会读成 749.0，去掉小数尾巴。"""
    text = value.strip()
    if text.replace(".", "", 1).isdigit() and "." in text:
        try:
            return str(int(float(text)))
        except ValueError:
            return text
    return text


def clean_ip(value: str) -> str:
    """防水等级：单元格常为 54 / 54.0，补成 IP54。"""
    text = value.strip()
    if not text:
        return text
    if text.upper().startswith("IP"):
        return text.upper()
    try:
        return f"IP{int(float(text))}"
    except ValueError:
        return text


def clean_customer_type(value: str) -> str:
    text = value.strip()
    if text in {"新", "NEW", "new"}:
        return "NEW"
    if text in {"老", "OLD", "old", "旧"}:
        return "OLD"
    return text


def clean_lead_time(value: str) -> str:
    """报价需时间：可能是 Excel 日期序列号，转成 YYYY-MM-DD。"""
    text = value.strip()
    try:
        num = float(text)
    except ValueError:
        return text
    if 30000 <= num <= 60000:
        return (EXCEL_EPOCH + dt.timedelta(days=num)).strftime("%Y-%m-%d")
    return text


STANDARD_LABELS: dict[str, str] = {
    "产品图片": "_image",
    "产品型号": "product_model",
    "产品功率": "power",
    "产品尺寸": "size",
    "输入电压": "voltage",
    "显色指数": "cri",
    "色温": "color_temp",
    "光通量": "lumen",
    "光通量/光效": "lumen",
    "光源": "light_source",
    "灯珠数量": "led_count",
    "IP": "waterproof",
    "主体": "main_body",
    "灯罩": "lamp_shade",
    "反光罩": "reflector",
    "功能": "feature",
    "电线插头": "plug",
    "需求数量": "quantity",
    "认证": "certification",
    "报价提供时间": "quote_lead_time",
    "其他要求": "other_requirement",
}

FOB_LABEL = "FOB(NINGBO) 含税RMB到宁波"


def parse_standard_block(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """解析「询价单填写模板（客户标准）」纵向块：字段为行、产品为列。"""
    start = -1
    for i, row in enumerate(rows):
        cells = [norm(c) for c in row[:1]]
        if cells and cells[0] == "产品图片":
            start = i
            break
    if start < 0:
        return []

    spec_rows: list[dict[str, Any]] = []
    blanks = 0
    for row in rows[start : start + 30]:
        cells = [norm(c) for c in row]
        if "产品型号" in cells and "功率" in cells:
            break
        label = cells[0] if cells else ""
        if not label:
            blanks += 1
            if blanks >= 2:
                break
            continue
        blanks = 0
        values = list(cells[1:])
        while values and not values[-1]:
            values.pop()
        if label not in STANDARD_LABELS and label != FOB_LABEL:
            continue
        spec_rows.append({"label": label, "values": values})
    return spec_rows


def apply_standard_block(spec_rows: list[dict[str, Any]], items: list[dict[str, Any]]) -> None:
    """把纵向块的列值按顺序回填到明细行（仅填空缺字段）。"""
    if not spec_rows or not items:
        return
    for spec in spec_rows:
        field = STANDARD_LABELS.get(str(spec["label"]))
        if not field or field == "_image":
            continue
        values = spec.get("values") or []
        for idx, item in enumerate(items):
            if idx >= len(values):
                break
            value = values[idx]
            if not value:
                continue
            if field == "quantity":
                try:
                    item["quantity"] = float(value)
                except ValueError:
                    continue
                continue
            if not item.get(field):
                item[field] = value


def standard_text(spec_rows: list[dict[str, Any]], label: str) -> str | None:
    for spec in spec_rows:
        if spec["label"] == label:
            values = [v for v in (spec.get("values") or []) if v]
            if values:
                return " ".join(values)
    return None


def items_from_standard_block(spec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """仅有「客户标准」纵向块的页签：按产品列反向生成明细行。"""
    if not spec_rows:
        return []
    width = max((len(s.get("values") or []) for s in spec_rows), default=0)
    if width <= 0:
        return []

    items: list[dict[str, Any]] = []
    for col in range(width):
        item: dict[str, Any] = {"group_type": "NEW", "unit": "PCS", "quantity": 0.0}
        for spec in spec_rows:
            field = STANDARD_LABELS.get(str(spec["label"]))
            if not field or field == "_image":
                continue
            values = spec.get("values") or []
            value = values[col] if col < len(values) else ""
            if not value:
                continue
            if field == "quantity":
                try:
                    item["quantity"] = float(value)
                except ValueError:
                    continue
            else:
                item[field] = value
        model = item.get("product_model") or item.get("power") or f"列{col + 1}"
        item["product_model"] = str(model)
        item.setdefault("product_name", str(model))
        items.append(item)
    return items


def parse_sheet(
    rows: list[list[Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    head: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    spec_rows = parse_standard_block(rows)

    header_idx = -1
    for i, row in enumerate(rows):
        labels = [norm(c) for c in row]
        if "询价单号" in labels:
            header_idx = i
            break
    if header_idx < 0:
        return head, items, spec_rows

    labels = [norm(c) for c in rows[header_idx]]
    values = rows[header_idx + 1] if header_idx + 1 < len(rows) else []
    for j, label in enumerate(labels):
        field = HEAD_ALIASES.get(label)
        if not field:
            continue
        raw = values[j] if j < len(values) else None
        if field in DATE_FIELDS:
            parsed = as_date(raw)
            if parsed:
                head[field] = parsed
        elif field in NUM_FIELDS:
            parsed_num = as_number(raw)
            if parsed_num is not None:
                head[field] = parsed_num
        else:
            text = norm(raw)
            if not is_placeholder(text):
                if field == "customer_code":
                    text = clean_code(text)
                elif field == "customer_type":
                    text = clean_customer_type(text)
                head[field] = text

    # 版本号：抬头区出现的形如 2022-04 / 2025-08（含换行）
    for row in rows[:6]:
        for cell in row:
            text = norm(cell).replace("\\n", "").replace("\n", "")
            if text.startswith("版本号"):
                head["version_no"] = text.split("：")[-1].split(":")[-1].strip()
                break

    block = 0
    j = header_idx + 1
    while j < len(rows):
        labels = [norm(c) for c in rows[j]]
        if "产品型号" in labels and "功率" in labels:
            block += 1
            group_type = "EXISTING" if "压框" in labels else "NEW"
            mapping = {idx: ITEM_ALIASES[label] for idx, label in enumerate(labels) if label in ITEM_ALIASES}
            j += 1
            empty_run = 0
            while j < len(rows):
                row = rows[j]
                cells = [norm(c) for c in row]
                if "产品型号" in cells and "功率" in cells:
                    break
                if not any(cells):
                    empty_run += 1
                    if empty_run >= 3:
                        break
                    j += 1
                    continue
                empty_run = 0
                item: dict[str, object] = {"group_type": group_type}
                for idx, field in mapping.items():
                    if field == "_picture" or idx >= len(row):
                        continue
                    raw = row[idx]
                    if field in NUM_FIELDS:
                        parsed_num = as_number(raw)
                        if parsed_num is not None:
                            item[field] = parsed_num
                    else:
                        text = norm(raw)
                        if text:
                            if field == "waterproof":
                                text = clean_ip(text)
                            elif field == "quote_lead_time":
                                text = clean_lead_time(text)
                            item[field] = text
                if item.get("product_model") or item.get("product_name"):
                    if not item.get("product_name"):
                        item["product_name"] = str(item.get("product_model") or "")
                    item.setdefault("unit", "PCS")
                    item.setdefault("quantity", 0)
                    item["_row"] = j
                    items.append(item)
                j += 1
            continue
        j += 1

    apply_standard_block(spec_rows, items)
    if not items and spec_rows:
        items = items_from_standard_block(spec_rows)
    return head, items, spec_rows


def load_sheets(path: str, limit: int | None) -> list[tuple[str, list[list[Any]]]]:
    wb = CalamineWorkbook.from_path(path)
    result: list[tuple[str, list[list[Any]]]] = []
    for name in wb.sheet_names:
        if name in SKIP_SHEETS:
            continue
        if limit is not None and len(result) >= limit:
            break
        try:
            result.append((name, wb.get_sheet_by_name(name).to_python()))
        except Exception:  # noqa: BLE001
            continue
    return result


async def apply_import(
    parsed: list[tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]],
) -> dict[str, int]:
    stats = {"inquiry": 0, "item": 0, "company_new": 0, "skipped": 0}
    async with async_session_factory() as db:
        users = {u.name: u for u in (await db.execute(select(User))).scalars().all()}

        for sheet, head, items, spec_rows in parsed:
            inquiry_no = str(head.get("inquiry_no") or "").strip() or f"JFX-{sheet}"
            exists = (await db.execute(select(Inquiry.id).where(Inquiry.inquiry_no == inquiry_no))).scalar_one_or_none()
            if exists:
                stats["skipped"] += 1
                continue

            company_id = None
            customer_name = str(head.get("customer_name") or "").strip()
            customer_code = clean_code(str(head.get("customer_code") or "").strip())
            owner = users.get(str(head.get("owner_name_text") or ""))
            if customer_name:
                company = (
                    (
                        await db.execute(
                            select(Company).where(Company.name == customer_name, Company.deleted_at.is_(None))
                        )
                    )
                    .scalars()
                    .first()
                )
                if company is None:
                    new_code, owner_seq, global_seq = await company_code.next_company_code(owner)
                    company = Company(
                        code=new_code,
                        owner_seq=owner_seq,
                        global_seq=global_seq,
                        name=customer_name,
                        name_en=customer_name,
                        remark=f"由历史询价单导入（{sheet}）；ERP 客户编号 {customer_code or '-'}",
                        sync_status="PENDING",
                    )
                    db.add(company)
                    await db.flush()
                    await company_code.ensure_primary_code(db, company)
                    if customer_code:
                        db.add(
                            BusinessCode(
                                company_id=company.id,
                                code=customer_code,
                                code_type="LEGACY",
                                remark="历史导入的 ERP 客户编号",
                            )
                        )
                    stats["company_new"] += 1
                company_id = company.id

            inquiry = Inquiry(
                inquiry_no=inquiry_no,
                company_id=company_id,
                source="IMPORT",
                currency="RMB",
                status="DRAFT",
                customer_code=customer_code or None,
                customer_name=customer_name or None,
                customer_type=str(head.get("customer_type") or "") or None,
                market=str(head.get("market") or "") or None,
                start_date=head.get("start_date"),
                end_date=head.get("end_date"),
                sample_date=head.get("sample_date"),
                order_date=head.get("order_date"),
                shipment_date=head.get("shipment_date"),
                first_order_amount=head.get("first_order_amount"),
                quantity_total=head.get("quantity_total"),
                annual_amount=head.get("annual_amount"),
                sample_lead_time=str(head.get("sample_lead_time") or "") or None,
                version_no=str(head.get("version_no") or "") or None,
                owner_name_text=str(head.get("owner_name_text") or "") or None,
                department_name_text=str(head.get("department_name_text") or "") or None,
                owner_id=owner.id if owner else None,
                department_id=owner.department_id if owner else None,
                spec_rows=spec_rows or None,
                requirement_text=standard_text(spec_rows, "其他要求"),
                trade_terms=FOB_LABEL if standard_text(spec_rows, FOB_LABEL) is not None else None,
            )
            db.add(inquiry)
            await db.flush()
            for idx, item in enumerate(items, start=1):
                payload = dict(item)
                payload.pop("_row", None)
                payload.setdefault("sort", idx)
                db.add(InquiryItem(inquiry_id=inquiry.id, **payload))
                stats["item"] += 1
            stats["inquiry"] += 1

        await db.commit()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    sheets = load_sheets(args.file, args.limit)
    parsed: list[tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = []
    failed: list[str] = []
    for name, rows in sheets:
        head, items, spec_rows = parse_sheet(rows)
        if not head.get("inquiry_no") and not items:
            failed.append(name)
            continue
        parsed.append((name, head, items, spec_rows))

    total_items = sum(len(i) for _, _, i, _ in parsed)
    with_no = sum(1 for _, h, _, _ in parsed if h.get("inquiry_no"))
    with_spec = sum(1 for _, _, _, s in parsed if s)
    print(f"[import] 解析页签 {len(sheets)} 个，成功 {len(parsed)}，无有效数据 {len(failed)}")
    print(f"[import] 含询价单号 {with_no}，含客户标准纵向块 {with_spec}，明细合计 {total_items} 行")
    if failed:
        print(f"[import] 未识别页签：{failed[:20]}{' ...' if len(failed) > 20 else ''}")

    for name, head, items, spec_rows in parsed[:5]:
        print(
            f"  - {name}: 单号={head.get('inquiry_no')} 客户={head.get('customer_name')} "
            f"业务员={head.get('owner_name_text')} 市场={head.get('market')} "
            f"明细={len(items)} 纵向块={len(spec_rows)}"
        )

    if args.verbose:
        name, head, items, spec_rows = parsed[0]
        print(f"\n===== 明细样例 {name} =====")
        print("HEAD:", head)
        print("SPEC:", spec_rows)
        for item in items[:8]:
            print("ITEM:", item)

    if not args.apply:
        print("[import] DRY-RUN，未写库（加 --apply 执行导入）")
        await engine.dispose()
        return

    stats = await apply_import(parsed)
    print(
        f"[import] 完成：询价单 {stats['inquiry']}，明细 {stats['item']}，"
        f"新建客户 {stats['company_new']}，跳过已存在 {stats['skipped']}"
    )

    # 顺带把 WPS 非标准路径（xl/drawings/media）里的产品图提取入库
    try:
        from app.db.import_inquiry_images import run as import_images

        print("[import] 开始回填产品图…")
        await import_images(args.file, True)
    except Exception as exc:  # noqa: BLE001
        print(f"[import] 产品图回填失败（可单独执行 app.db.import_inquiry_images）：{exc}")

    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
    sys.exit(0)
