"""M3 跟进记录接口。"""

from app.api.crud import CrudConfig, build_crud_router
from app.models.business import Activity
from app.schemas.business import ActivityCreate, ActivityOut, ActivityUpdate

router = build_crud_router(
    CrudConfig(
        model=Activity,
        prefix="/activities",
        tag="M3-跟进记录",
        name="跟进记录",
        create_schema=ActivityCreate,
        update_schema=ActivityUpdate,
        out_schema=ActivityOut,
        view_permission="opportunity:view",
        create_permission="opportunity:update",
        update_permission="opportunity:update",
        delete_permission="opportunity:update",
        search_fields=("content",),
        filter_fields={
            "biz_type": "biz_type",
            "biz_id": "biz_id",
            "company_id": "company_id",
            "opportunity_id": "opportunity_id",
            "type": "type",
        },
        order_field="created_at",
        description="客户/商机跟进记录",
    )
)
