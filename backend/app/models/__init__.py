"""模型聚合导出：供 Alembic autogenerate 与业务引用。"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.business import (
    Activity,
    BusinessCode,
    Company,
    Contact,
    Inquiry,
    InquiryItem,
    Lead,
    Opportunity,
    Product,
    Sku,
    Task,
)
from app.models.email import (
    EmailAccount,
    EmailAttachment,
    EmailMessage,
    EmailThread,
    File,
)
from app.models.integration import (
    IntegrationLog,
    IntegrationOutbox,
    K3CustomerStaging,
    K3OrderStaging,
)
from app.models.pricing import (
    ApprovalInstance,
    ApprovalLog,
    ApprovalTask,
    PricingRecord,
    PricingRule,
    Quotation,
    QuotationItem,
)
from app.models.sales import (
    Feedback,
    FeedbackFollowup,
    InquiryStatusLog,
    QuoteLibrary,
    SalesOrder,
    Sample,
    SyncConflict,
)
from app.models.support import (
    Dictionary,
    FeatureFlag,
    NumberSequence,
    SystemConfig,
)
from app.models.user import (
    DataScope,
    Department,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

__all__ = [
    "Base",
    # 系统
    "AuditLog",
    "Dictionary",
    "FeatureFlag",
    "NumberSequence",
    "SystemConfig",
    "DataScope",
    "Department",
    "Permission",
    "Role",
    "RolePermission",
    "User",
    "UserRole",
    # M2 客户中心
    "Lead",
    "Company",
    "Contact",
    "BusinessCode",
    # M3 销售主链路
    "Opportunity",
    "Product",
    "Sku",
    "Inquiry",
    "InquiryItem",
    "Activity",
    "Task",
    # M4 询报价闭环
    "PricingRecord",
    "PricingRule",
    "Quotation",
    "QuotationItem",
    "ApprovalInstance",
    "ApprovalTask",
    "ApprovalLog",
    # 销售中心 6 模块（PAND-249）
    "SalesOrder",
    "Sample",
    "QuoteLibrary",
    "Feedback",
    "FeedbackFollowup",
    "SyncConflict",
    "InquiryStatusLog",
    # M5 邮件
    "File",
    "EmailAccount",
    "EmailThread",
    "EmailMessage",
    "EmailAttachment",
    # M6 集成
    "IntegrationLog",
    "IntegrationOutbox",
    "K3CustomerStaging",
    "K3OrderStaging",
]
