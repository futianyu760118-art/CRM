"""报价单 PDF 生成（M4）。

主路径：Playwright HTML → PDF（外贸报价单样式）。
降级路径：reportlab 直接排版（无需浏览器，中文字体使用内置 CID 字体）。
两条路径产出同样的业务字段，接口层无需感知。
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

from app.services.pricing import COST_FIELDS  # noqa: F401  (保持模块依赖清晰)

# ------------------------------------------------------------------ HTML 模板

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>Quotation {quotation_no}</title>
<style>
  body {{ font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; color: #222; font-size: 12px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; }}
  .company {{ font-size: 20px; font-weight: 700; }}
  .muted {{ color: #666; }}
  h1 {{ text-align: center; font-size: 22px; letter-spacing: 4px; margin: 18px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 8px; }}
  th {{ background: #f5f5f5; text-align: left; }}
  .right {{ text-align: right; }}
  .total {{ font-weight: 700; font-size: 14px; }}
  .terms {{ margin-top: 16px; }}
  .terms td {{ border: none; padding: 3px 0; }}
  .signature {{ margin-top: 40px; display: flex; justify-content: space-between; }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="company">{seller_name}</div>
      <div class="muted">{seller_address}</div>
      <div class="muted">{seller_contact}</div>
    </div>
    <div class="right">
      <div><b>QUOTATION</b></div>
      <div class="muted">No. {quotation_no}</div>
      <div class="muted">Date: {quote_date}</div>
      <div class="muted">Valid until: {valid_until}</div>
    </div>
  </div>

  <h1>报 价 单</h1>

  <table>
    <tr><th style="width:120px">Customer</th><td>{customer_name}</td>
        <th style="width:120px">Attn.</th><td>{contact_name}</td></tr>
    <tr><th>Country</th><td>{customer_country}</td>
        <th>Currency</th><td>{currency}</td></tr>
  </table>

  <table>
    <thead>
      <tr>
        <th style="width:40px">#</th><th>Product</th><th>Specification</th>
        <th class="right" style="width:80px">Qty</th><th style="width:60px">Unit</th>
        <th class="right" style="width:90px">Unit Price</th>
        <th class="right" style="width:100px">Amount</th>
      </tr>
    </thead>
    <tbody>
      {item_rows}
    </tbody>
    <tfoot>
      <tr><td colspan="6" class="right">Subtotal</td>
          <td class="right">{subtotal}</td></tr>
      <tr><td colspan="6" class="right">Additional Fee</td>
          <td class="right">{additional_fee}</td></tr>
      <tr><td colspan="6" class="right">Discount</td>
          <td class="right">-{discount}</td></tr>
      <tr><td colspan="6" class="right">Tax</td>
          <td class="right">{tax_amount}</td></tr>
      <tr><td colspan="6" class="right total">TOTAL ({currency})</td>
          <td class="right total">{total_amount}</td></tr>
    </tfoot>
  </table>

  <table class="terms">
    <tr><th style="width:130px">Trade Terms</th><td>{incoterm}</td></tr>
    <tr><th>Payment Terms</th><td>{payment_terms}</td></tr>
    <tr><th>Warranty</th><td>{warranty}</td></tr>
    <tr><th>Remarks</th><td>{remark}</td></tr>
  </table>

  <div class="signature">
    <div>Buyer: ______________________</div>
    <div>Seller: ______________________</div>
  </div>
</body>
</html>
"""


def _fmt(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def render_html(context: dict[str, Any]) -> str:
    items = context.get("items") or []
    rows = []
    for idx, item in enumerate(items, start=1):
        rows.append(
            "<tr>"
            f'<td class="right">{idx}</td>'
            f"<td>{item.get('product_name') or ''}</td>"
            f"<td>{item.get('spec') or ''}</td>"
            f'<td class="right">{_fmt(item.get("quantity"), 0)}</td>'
            f"<td>{item.get('unit') or ''}</td>"
            f'<td class="right">{_fmt(item.get("unit_price"), 4)}</td>'
            f'<td class="right">{_fmt(item.get("amount"), 2)}</td>'
            "</tr>"
        )
    data = dict(context)
    data["item_rows"] = "\n".join(rows) or '<tr><td colspan="7">-</td></tr>'
    for key in ("subtotal", "additional_fee", "discount", "tax_amount", "total_amount"):
        data[key] = _fmt(context.get(key))
    for key in (
        "seller_name",
        "seller_address",
        "seller_contact",
        "quotation_no",
        "quote_date",
        "valid_until",
        "customer_name",
        "contact_name",
        "customer_country",
        "currency",
        "incoterm",
        "payment_terms",
        "warranty",
        "remark",
    ):
        data[key] = context.get(key) or "-"
    return _HTML_TEMPLATE.format(**data)


# ------------------------------------------------------------------ 生成器


def _try_playwright(html: str) -> bytes | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                return page.pdf(format="A4", print_background=True)
            finally:
                browser.close()
    except Exception:  # noqa: BLE001
        return None


def _reportlab_pdf(context: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    except Exception:  # noqa: BLE001
        font = "Helvetica"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Quotation {context.get('quotation_no')}",
    )
    title_style = ParagraphStyle("title", fontName=font, fontSize=18, leading=24, alignment=1)
    label_style = ParagraphStyle("label", fontName=font, fontSize=9, textColor=colors.HexColor("#666666"))
    body_style = ParagraphStyle("body", fontName=font, fontSize=9, leading=13)

    story: list[Any] = []
    story.append(Paragraph(str(context.get("seller_name") or ""), body_style))
    story.append(Paragraph(str(context.get("seller_address") or ""), label_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph("报 价 单 / QUOTATION", title_style))
    story.append(Spacer(1, 10))

    header = [
        [
            Paragraph("单号 No.", label_style),
            Paragraph(str(context.get("quotation_no") or "-"), body_style),
            Paragraph("日期 Date", label_style),
            Paragraph(str(context.get("quote_date") or "-"), body_style),
        ],
        [
            Paragraph("客户 Customer", label_style),
            Paragraph(str(context.get("customer_name") or "-"), body_style),
            Paragraph("有效期 Valid until", label_style),
            Paragraph(str(context.get("valid_until") or "-"), body_style),
        ],
        [
            Paragraph("联系人 Attn.", label_style),
            Paragraph(str(context.get("contact_name") or "-"), body_style),
            Paragraph("币种 Currency", label_style),
            Paragraph(str(context.get("currency") or "-"), body_style),
        ],
    ]
    t = Table(header, colWidths=[28 * mm, 62 * mm, 30 * mm, 60 * mm])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F5F5")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F5F5F5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    rows = [
        [
            Paragraph("#", label_style),
            Paragraph("Product 产品", label_style),
            Paragraph("Spec 规格", label_style),
            Paragraph("Qty", label_style),
            Paragraph("Unit", label_style),
            Paragraph("Unit Price", label_style),
            Paragraph("Amount", label_style),
        ]
    ]
    for idx, item in enumerate(context.get("items") or [], start=1):
        rows.append(
            [
                Paragraph(str(idx), body_style),
                Paragraph(str(item.get("product_name") or ""), body_style),
                Paragraph(str(item.get("spec") or ""), body_style),
                Paragraph(_fmt(item.get("quantity"), 0), body_style),
                Paragraph(str(item.get("unit") or ""), body_style),
                Paragraph(_fmt(item.get("unit_price"), 4), body_style),
                Paragraph(_fmt(item.get("amount"), 2), body_style),
            ]
        )
    for label, key, negate in (
        ("小计 Subtotal", "subtotal", False),
        ("附加费 Additional Fee", "additional_fee", False),
        ("折扣 Discount", "discount", True),
        ("税额 Tax", "tax_amount", False),
    ):
        rows.append(
            [
                Paragraph("", body_style),
                Paragraph(label, body_style),
                Paragraph("", body_style),
                Paragraph("", body_style),
                Paragraph("", body_style),
                Paragraph("", body_style),
                Paragraph(("-" if negate else "") + _fmt(context.get(key)), body_style),
            ]
        )
    rows.append(
        [
            Paragraph("", body_style),
            Paragraph(f"合计 TOTAL ({context.get('currency') or ''})", body_style),
            Paragraph("", body_style),
            Paragraph("", body_style),
            Paragraph("", body_style),
            Paragraph("", body_style),
            Paragraph(_fmt(context.get("total_amount")), body_style),
        ]
    )

    table = Table(
        rows,
        colWidths=[10 * mm, 48 * mm, 42 * mm, 16 * mm, 14 * mm, 24 * mm, 26 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (3, 1), (6, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), font),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    terms = [
        ["贸易术语 Trade Terms", str(context.get("incoterm") or "-")],
        ["付款条件 Payment Terms", str(context.get("payment_terms") or "-")],
        ["质保 Warranty", str(context.get("warranty") or "-")],
        ["备注 Remarks", str(context.get("remark") or "-")],
    ]
    tt = Table(
        [[Paragraph(a, label_style), Paragraph(b, body_style)] for a, b in terms],
        colWidths=[42 * mm, 138 * mm],
    )
    tt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(tt)
    story.append(Spacer(1, 24))
    story.append(Paragraph("买方 Buyer: ____________________　　　　　卖方 Seller: ____________________", body_style))

    doc.build(story)
    return buf.getvalue()


def build_quotation_pdf(context: dict[str, Any]) -> tuple[bytes, str]:
    """返回 (pdf 字节, 使用的生成器名称)。"""
    html = render_html(context)
    data = _try_playwright(html)
    if data:
        return data, "playwright"
    return _reportlab_pdf(context), "reportlab"


# ------------------------------------------------------------------ 对外价格表

_PRICE_LIST_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<style>
  body {{ font-family: Arial, "Microsoft YaHei", sans-serif; font-size: 10px; color: #000; }}
  .seller {{ font-size: 15px; font-weight: 700; }}
  .muted {{ color: #444; }}
  .title {{ font-size: 14px; font-weight: 700; margin: 14px 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ border: 1px solid #888; padding: 4px 5px; vertical-align: top; }}
  th {{ background: #f0f0f0; text-align: center; font-size: 9px; }}
  td.desc {{ white-space: pre-wrap; }}
  td.num {{ text-align: right; }}
  td.pic {{ text-align: center; }}
  td.pic img {{ max-width: 70px; max-height: 60px; }}
  .terms {{ margin-top: 10px; }}
  .terms div {{ margin-bottom: 3px; }}
  .notes {{ margin-top: 10px; white-space: pre-wrap; }}
</style>
</head>
<body>
  <div class="seller">{seller_name}</div>
  <div class="muted">Add: {seller_address}</div>
  <div class="muted">{seller_contact}</div>
  <div class="muted">To: {customer_name}{buyer_attn}</div>

  <div class="title">{title}</div>

  <table>
    <thead>
      <tr>
        <th style="width:16%">Item No.</th>
        <th style="width:9%">Picture</th>
        <th style="width:31%">Description of Goods</th>
        <th style="width:8%">Price<br>({currency})</th>
        <th style="width:6%">MOQ</th>
        <th style="width:6%">Power<br>(W)</th>
        <th style="width:5%">IP</th>
        <th style="width:7%">Lumen<br>(lm)</th>
        <th style="width:8%">Color<br>TEMP.</th>
        <th style="width:8%">Color<br>Rendering<br>(Ra)</th>
        <th style="width:8%">Price<br>Valid</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <div class="terms">
    {terms}
  </div>

  <div class="notes">{notes_cn}</div>
  <div class="notes">{notes_en}</div>
</body>
</html>
"""


def _esc(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def render_price_list_html(context: dict[str, Any]) -> str:
    rows = []
    for item in context.get("items") or []:
        picture = item.get("picture")
        pic_cell = f'<img src="{picture}" />' if picture else ""
        rows.append(
            "<tr>"
            f"<td>{_esc(item.get('item_no'))}</td>"
            f'<td class="pic">{pic_cell}</td>'
            f'<td class="desc">{_esc(item.get("description"))}</td>'
            f'<td class="num">{_fmt(item.get("unit_price"))}</td>'
            f"<td>{_esc(item.get('moq'))}</td>"
            f"<td>{_esc(item.get('power'))}</td>"
            f"<td>{_esc(item.get('ip'))}</td>"
            f"<td>{_esc(item.get('lumen'))}</td>"
            f"<td>{_esc(item.get('color_temp'))}</td>"
            f"<td>{_esc(item.get('color_rendering'))}</td>"
            f"<td>{_esc(item.get('price_valid'))}</td>"
            "</tr>"
        )
    terms = "\n".join(f"<div>{_esc(t)}</div>" for t in (context.get("terms") or []))
    return _PRICE_LIST_TEMPLATE.format(
        seller_name=_esc(context.get("seller_name")),
        seller_address=_esc(context.get("seller_address")),
        seller_contact=_esc(context.get("seller_contact")),
        customer_name=_esc(context.get("customer_name")),
        buyer_attn=_esc(context.get("buyer_attn") or ""),
        title=_esc(context.get("title") or "Offer"),
        currency=_esc(context.get("currency") or "RMB"),
        rows="\n".join(rows) or '<tr><td colspan="11">-</td></tr>',
        terms=terms,
        notes_cn=_esc(context.get("notes_cn")),
        notes_en=_esc(context.get("notes_en")),
    )


def _reportlab_price_list(context: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    except Exception:  # noqa: BLE001
        font = "Helvetica"

    body = ParagraphStyle("body", fontName=font, fontSize=7.5, leading=10)
    small = ParagraphStyle("small", fontName=font, fontSize=7, leading=9, textColor=colors.HexColor("#444444"))
    title_style = ParagraphStyle("t", fontName=font, fontSize=13, leading=16, spaceAfter=6)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=str(context.get("title") or "Offer"),
    )

    story: list[Any] = []
    story.append(
        Paragraph(_esc(context.get("seller_name")), ParagraphStyle("s", fontName=font, fontSize=13, leading=16))
    )
    story.append(Paragraph(f"Add: {_esc(context.get('seller_address'))}", small))
    story.append(Paragraph(_esc(context.get("seller_contact")), small))
    story.append(Spacer(1, 6))
    story.append(Paragraph(_esc(context.get("title") or "Offer"), title_style))

    head = [
        "Item No.",
        "Picture",
        "Description of Goods",
        f"Price ({context.get('currency') or 'RMB'})",
        "MOQ",
        "Power (W)",
        "IP",
        "Lumen (lm)",
        "Color TEMP.",
        "Color Rendering (Ra)",
        "Price Valid",
    ]
    data = [[Paragraph(h, small) for h in head]]
    for item in context.get("items") or []:
        data.append(
            [
                Paragraph(_esc(item.get("item_no")), body),
                "",
                Paragraph(_esc(item.get("description")), body),
                Paragraph(_fmt(item.get("unit_price")), body),
                Paragraph(_esc(item.get("moq")), body),
                Paragraph(_esc(item.get("power")), body),
                Paragraph(_esc(item.get("ip")), body),
                Paragraph(_esc(item.get("lumen")), body),
                Paragraph(_esc(item.get("color_temp")), body),
                Paragraph(_esc(item.get("color_rendering")), body),
                Paragraph(_esc(item.get("price_valid")), body),
            ]
        )

    table = Table(
        data,
        colWidths=[30 * mm, 20 * mm, 62 * mm, 22 * mm, 16 * mm, 17 * mm, 12 * mm, 20 * mm, 22 * mm, 24 * mm, 20 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#888888")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), font),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))
    for term in context.get("terms") or []:
        story.append(Paragraph(_esc(term), small))
    story.append(Spacer(1, 6))
    if context.get("notes_cn"):
        story.append(Paragraph(_esc(context["notes_cn"]), small))
    if context.get("notes_en"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(_esc(context["notes_en"]), small))

    doc.build(story)
    return buf.getvalue()


def build_price_list_pdf(context: dict[str, Any]) -> tuple[bytes, str]:
    html = render_price_list_html(context)
    data = _try_playwright(html)
    if data:
        return data, "playwright"
    return _reportlab_price_list(context), "reportlab"


def build_context(
    *,
    seller: dict[str, Any],
    quotation: dict[str, Any],
    customer: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    today = date.today().isoformat()
    return {
        "seller_name": seller.get("name") or "",
        "seller_address": seller.get("address") or "",
        "seller_contact": seller.get("contact") or "",
        "quotation_no": quotation.get("quotation_no"),
        "quote_date": quotation.get("created_at") or today,
        "valid_until": quotation.get("valid_until") or "",
        "customer_name": customer.get("name") or "",
        "contact_name": customer.get("contact_name") or "",
        "customer_country": customer.get("country") or "",
        "currency": quotation.get("currency") or "USD",
        "incoterm": quotation.get("incoterm"),
        "payment_terms": quotation.get("payment_terms"),
        "warranty": quotation.get("warranty"),
        "remark": quotation.get("remark"),
        "subtotal": quotation.get("subtotal"),
        "additional_fee": quotation.get("additional_fee"),
        "discount": quotation.get("discount"),
        "tax_amount": quotation.get("tax_amount"),
        "total_amount": quotation.get("total_amount"),
        "items": items,
    }
