"""字段中文名映射（PAND-314 架构决策 D2）。

校验错误统一输出「<字段中文名>：<原因>」，界面不得出现英文字段名。
开发A（PAND-315）建设本文件；开发B（PAND-316）的商机/样品字段也在这里登记。
"""

from __future__ import annotations

FIELD_LABELS: dict[str, str] = {
    # 通用
    "id": "ID",
    "name": "名称",
    "code": "编码",
    "status": "状态",
    "remark": "备注",
    "owner_id": "负责人",
    "department_id": "部门",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    # 线索
    "lead_no": "线索编号",
    "contact_name": "联系人",
    "email": "邮箱",
    "phone": "电话",
    "mobile": "手机",
    "country": "国家",
    "industry": "行业",
    "source": "来源",
    "requirement_text": "具体需求内容",
    "lead_level": "线索等级",
    "background": "初步背景调查",
    "channel": "客户渠道分类",
    "force": "确认查重",
    "dedup_note": "查重说明",
    "create_contact": "创建联系人",
    "customer_level": "客户等级",
    "link_company_id": "关联客户",
    "non_duplicate_reason": "非重复说明",
    # 客户
    "name_en": "英文名称",
    "website": "官网",
    "address": "地址",
    "currency": "币种",
    "customer_type": "客户类型",
    "company_background": "公司背景",
    "main_products": "主营产品",
    "brand": "品牌",
    "sales_channel_market": "销售渠道及市场",
    "payment_method": "付款方式",
    "customer_status": "客户状态",
    # 联系人
    "company_id": "所属客户",
    "position": "职位",
    "wechat": "微信",
    "whatsapp": "WhatsApp",
    "is_primary": "主要联系人",
    "relation_type": "关系类型",
    "link_to_existing_id": "关联联系人",
    "force_independent": "独立联系人",
    # 商机（开发B 共用）
    "requirement": "需求描述",
    "estimated_amount": "预计金额",
    "product_category": "产品类别",
    "quantity": "数量",
    "inquiry_id": "关联询价单",
    "pricing_id": "关联核价记录",
    "quotation_amount": "报价金额",
    "sample_record": "样品记录",
    "negotiation_record": "谈判记录",
    "won_amount": "成交金额",
    "lost_reason": "流失原因",
    "stage": "目标阶段",
    # 样品（开发B 共用）
    "product_model": "产品型号",
    "sample_requirement": "样品要求",
    "plan_date": "计划完成日期",
    "courier": "快递公司",
    "tracking_no": "快递单号",
    "feedback": "客户反馈",
    "feedback_date": "反馈日期",
    "send_date": "寄出日期",
    "opportunity_id": "关联商机",
    # 产品资料（开发B 共用）
    "doc_type": "资料类型",
    "version_no": "版本号",
    "filename": "文件名",
    "file_id": "文件",
    "qty_from": "数量条件（起）",
    "qty_to": "数量条件（止）",
    "unit_price": "单价",
    "valid_from": "有效期（起）",
    "valid_to": "有效期（止）",
}


def field_label(field: str | None) -> str:
    if not field:
        return ""
    return FIELD_LABELS.get(field, field)
