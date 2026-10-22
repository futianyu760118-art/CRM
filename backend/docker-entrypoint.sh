#!/bin/sh
# 启动前执行数据库迁移与幂等种子数据，再交给 CMD（uvicorn）。
set -eu

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] seed default data"
python -m app.db.seed

exec "$@"
