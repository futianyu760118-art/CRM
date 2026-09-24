"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    activities,
    approvals,
    audit_logs,
    auth,
    companies,
    contacts,
    dashboard,
    departments,
    emails,
    files,
    inquiries,
    integrations,
    leads,
    opportunities,
    pricing,
    products,
    quotations,
    roles,
    system,
    tasks,
    users,
)

api_router = APIRouter()

# 系统 / 认证
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(departments.router)
api_router.include_router(system.dict_router)
api_router.include_router(system.flag_router)
api_router.include_router(audit_logs.router)

# M2 客户中心
api_router.include_router(leads.router)
api_router.include_router(companies.router)
api_router.include_router(contacts.router)

# M3 销售主链路
api_router.include_router(opportunities.router)
api_router.include_router(products.router)
api_router.include_router(inquiries.router)
api_router.include_router(activities.router)
api_router.include_router(tasks.router)

# M4 询报价闭环
api_router.include_router(pricing.router)
api_router.include_router(pricing.rules_router)
api_router.include_router(quotations.router)
api_router.include_router(approvals.router)

# M5 邮件闭环
api_router.include_router(emails.account_router)
api_router.include_router(emails.mail_router)

# M6 K3 集成
api_router.include_router(integrations.router)

# 通用文件
api_router.include_router(files.router)
