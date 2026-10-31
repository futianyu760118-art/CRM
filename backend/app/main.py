"""FastAPI 应用入口（M1 系统骨架）。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core import response as resp
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.redis_client import get_redis
from app.db.session import engine
from app.middleware.audit import AuditMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.services.number_sequence import ensure_sequence_floors

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    logger.info("%s v%s 启动中 (ENV=%s)", settings.APP_NAME, settings.APP_VERSION, settings.ENV)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL 连接正常")
    except Exception as exc:  # noqa: BLE001
        logger.warning("PostgreSQL 连接失败: %s", exc)
    try:
        await get_redis().ping()
        logger.info("Redis 连接正常")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis 连接失败: %s", exc)

    try:
        floors = await ensure_sequence_floors()
        logger.info("编号序列已对齐: %s", floors)
    except Exception as exc:  # noqa: BLE001
        logger.warning("编号序列对齐失败: %s", exc)
    yield
    await engine.dispose()
    logger.info("应用已关闭")


tags_metadata = [
    {"name": "认证", "description": "登录 / 刷新 Token / 登出 / 当前用户"},
    {"name": "工作台", "description": "Dashboard 概览与系统元数据"},
    {"name": "系统-用户", "description": "用户管理"},
    {"name": "系统-角色权限", "description": "角色、权限点、数据范围"},
    {"name": "系统-部门", "description": "组织架构"},
    {"name": "系统-字典", "description": "数据字典"},
    {"name": "系统-功能开关", "description": "Feature Flag"},
    {"name": "系统-审计日志", "description": "操作审计"},
]

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="外贸销售CRM及询报价管理平台 - 后端 API（项目编号 CRM-2026-001）",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(AuditMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["系统"], summary="健康检查")
async def health() -> dict:
    db_ok, redis_ok = False, False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        pass
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:  # noqa: BLE001
        pass
    return resp.ok(
        {
            "status": "ok" if (db_ok and redis_ok) else "degraded",
            "version": settings.APP_VERSION,
            "env": settings.ENV,
            "postgres": db_ok,
            "redis": redis_ok,
        }
    )
