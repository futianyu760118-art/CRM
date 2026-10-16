"""权限点定义与初始化模板（DOC-PRD-001 § 6 权限矩阵）。"""

from __future__ import annotations

from typing import Any


def _menu(
    code: str,
    name: str,
    path: str,
    icon: str | None = None,
    sort: int = 0,
) -> dict[str, Any]:
    return {"code": code, "name": name, "type": "MENU", "path": path, "icon": icon, "sort": sort}


def _button(code: str, name: str) -> dict[str, Any]:
    return {"code": code, "name": name, "type": "BUTTON"}


# 权限点：module -> 菜单 + 按钮
# 类型：MENU（菜单）/ BUTTON（按钮）
PERMISSIONS: list[dict[str, Any]] = [
    _menu("dashboard:view", "工作台", "/dashboard", "DashboardOutlined", 10),
    # 线索
    _menu("lead:view", "线索查看", "/leads", "FunnelPlotOutlined", 20),
    _button("lead:create", "线索创建"),
    _button("lead:update", "线索编辑"),
    _button("lead:delete", "线索删除"),
    _button("lead:assign", "线索分配"),
    _button("lead:convert", "线索转客户"),
    # 客户
    _menu("customer:view", "客户查看", "/customers", "TeamOutlined", 30),
    _button("customer:create", "客户创建"),
    _button("customer:update", "客户编辑"),
    _button("customer:delete", "客户删除"),
    _button("customer:merge", "客户合并"),
    # 联系人
    _menu("contact:view", "联系人查看", "/contacts", "ContactsOutlined", 40),
    _button("contact:create", "联系人创建"),
    _button("contact:update", "联系人编辑"),
    _button("contact:delete", "联系人删除"),
    # 商机
    _menu("opportunity:view", "商机查看", "/opportunities", "AimOutlined", 50),
    _button("opportunity:create", "商机创建"),
    _button("opportunity:update", "商机编辑"),
    _button("opportunity:delete", "商机删除"),
    _button("opportunity:stage", "商机阶段流转"),
    # 产品
    _menu("product:view", "产品查看", "/products", "AppstoreOutlined", 60),
    _button("product:create", "产品创建"),
    _button("product:update", "产品编辑"),
    _button("product:delete", "产品删除"),
    # 询价
    _menu("inquiry:view", "询价查看", "/inquiries", "FileSearchOutlined", 70),
    _button("inquiry:create", "询价创建"),
    _button("inquiry:update", "询价编辑"),
    _button("inquiry:submit", "询价提交"),
    _button("inquiry:price", "询价核价字段"),
    _button("inquiry:status", "询价状态流转"),
    _button("inquiry:import", "询价导入"),
    _button("inquiry:export", "询价导出"),
    _button("inquiry:delete", "询价删除"),
    # 核价
    _menu("pricing:view", "核价查看", "/pricing", "CalculatorOutlined", 80),
    _button("pricing:cost_view", "成本字段查看"),
    _button("pricing:floor_view", "底价字段查看"),
    _button("pricing:create", "核价创建"),
    _button("pricing:submit", "核价提交"),
    _button("pricing:approve", "核价审批"),
    # 报价
    _menu("quotation:view", "报价查看", "/quotations", "ProfileOutlined", 90),
    _button("quotation:create", "报价创建"),
    _button("quotation:update", "报价编辑"),
    _button("quotation:submit", "报价提交"),
    _button("quotation:approve", "报价审批"),
    _button("quotation:pdf", "报价PDF生成"),
    _button("quotation:send", "报价邮件发送"),
    # 审批
    _menu("approval:view", "审批查看", "/approvals", "AuditOutlined", 100),
    _button("approval:approve", "审批通过"),
    _button("approval:reject", "审批驳回"),
    # 邮件
    _menu("email:view", "邮件查看", "/emails", "MailOutlined", 110),
    _button("email:send", "邮件发送"),
    _button("email:sync", "邮件同步"),
    # 任务
    _menu("task:view", "任务查看", "/tasks", "CheckSquareOutlined", 120),
    _button("task:create", "任务创建"),
    # 销售中心 6 模块（PAND-249）
    _menu("order:view", "订单管理", "/orders", "ShoppingCartOutlined", 140),
    _button("order:create", "订单创建"),
    _button("order:update", "订单编辑"),
    _button("order:status", "订单状态流转"),
    _button("order:delete", "订单删除"),
    _menu("sample:view", "样品管理", "/samples", "ExperimentOutlined", 150),
    _button("sample:create", "样品创建"),
    _button("sample:update", "样品编辑"),
    _button("sample:status", "样品状态流转"),
    _button("sample:delete", "样品删除"),
    _menu("quote:view", "报价库", "/quote-library", "GoldOutlined", 160),
    _button("quote:manage", "报价库维护"),
    _button("quote:delete", "报价库删除"),
    _menu("feedback:view", "问题反馈", "/feedback", "BugOutlined", 170),
    _button("feedback:create", "反馈创建"),
    _button("feedback:handle", "反馈处理"),
    _button("feedback:delete", "反馈删除"),
    # 集成
    _menu("integration:view", "K3集成日志", "/integrations/k3/logs", "ApiOutlined", 130),
    # 系统设置
    _menu("system:view", "系统设置", "/settings", "SettingOutlined", 900),
    _menu("user:view", "用户查看", "/settings/users", None, 910),
    _button("user:create", "用户创建"),
    _button("user:update", "用户编辑"),
    _menu("role:view", "角色查看", "/settings/roles", None, 920),
    _button("role:update", "角色编辑"),
    _menu("department:view", "部门查看", "/settings/departments", None, 930),
    _button("department:update", "部门编辑"),
    _menu("dictionary:view", "字典查看", "/settings/dictionaries", None, 940),
    _menu("audit:view", "审计日志", "/settings/audit-logs", None, 950),
    _menu("feature_flag:view", "功能开关", "/settings/feature-flags", None, 960),
    _button("feature_flag:update", "功能开关编辑"),
]

ALL_PERMISSION_CODES = [p["code"] for p in PERMISSIONS]


def _codes(prefix: str) -> list[str]:
    return [c for c in ALL_PERMISSION_CODES if c.startswith(prefix)]


# 角色模板：code -> (名称, 权限, 数据范围)
ROLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "admin": {
        "name": "系统管理员",
        "description": "用户管理、权限配置、系统配置",
        "permissions": ["*"],
        "scope_type": "ALL",
    },
    "boss": {
        "name": "老板/总经理",
        "description": "全局数据查看、重大报价审批",
        "permissions": _codes("dashboard")
        + _codes("lead")
        + _codes("customer")
        + _codes("contact")
        + _codes("opportunity")
        + _codes("product")
        + _codes("inquiry")
        + _codes("pricing")
        + _codes("quotation")
        + _codes("approval")
        + _codes("email")
        + _codes("task")
        + _codes("order")
        + _codes("sample")
        + _codes("quote")
        + _codes("feedback")
        + _codes("integration")
        + ["audit:view"],
        "scope_type": "ALL",
    },
    "manager": {
        "name": "销售主管",
        "description": "部门数据、线索分配、报价审批",
        "permissions": _codes("dashboard")
        + _codes("lead")
        + _codes("customer")
        + _codes("contact")
        + _codes("opportunity")
        + _codes("product")
        + _codes("inquiry")
        + ["pricing:view", "pricing:cost_view", "pricing:floor_view", "pricing:approve"]
        + _codes("quotation")
        + _codes("approval")
        + _codes("email")
        + _codes("task")
        + _codes("order")
        + _codes("sample")
        + _codes("quote")
        + _codes("feedback"),
        "scope_type": "DEPT_AND_CHILD",
    },
    "sales": {
        "name": "业务员",
        "description": "管客户、跟商机、发报价、记跟进",
        "permissions": [
            "dashboard:view",
            "lead:view",
            "lead:create",
            "lead:update",
            "lead:convert",
            "customer:view",
            "customer:create",
            "customer:update",
            "contact:view",
            "contact:create",
            "contact:update",
            "opportunity:view",
            "opportunity:create",
            "opportunity:update",
            "opportunity:stage",
            "product:view",
            "inquiry:view",
            "inquiry:create",
            "inquiry:update",
            "inquiry:submit",
            "pricing:view",
            "pricing:floor_view",
            "quotation:view",
            "quotation:create",
            "quotation:update",
            "quotation:submit",
            "quotation:pdf",
            "quotation:send",
            "approval:view",
            "email:view",
            "email:send",
            "email:sync",
            "order:view",
            "order:create",
            "order:update",
            "order:status",
            "sample:view",
            "sample:create",
            "sample:update",
            "sample:status",
            "quote:view",
            "feedback:view",
            "feedback:create",
            "task:view",
            "task:create",
        ],
        "scope_type": "SELF",
    },
    "pricing": {
        "name": "核价员",
        "description": "核算成本、提交核价版本",
        "permissions": [
            "dashboard:view",
            "customer:view",
            "contact:view",
            "opportunity:view",
            "product:view",
            "product:create",
            "product:update",
            "inquiry:view",
            "pricing:view",
            "pricing:cost_view",
            "pricing:floor_view",
            "pricing:create",
            "pricing:submit",
            "pricing:approve",
            "quotation:view",
            "task:view",
        ],
        "scope_type": "ALL",
    },
}
