# 启动基础设施：PostgreSQL / Redis / MinIO
$root = Join-Path $PSScriptRoot '..'
Set-Location $root
docker compose up -d
docker compose ps
