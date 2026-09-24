# 一键初始化后端：建 venv、装依赖、迁移、灌种子数据
$ErrorActionPreference = 'Stop'
$backend = Join-Path $PSScriptRoot '..\backend'
Set-Location $backend

if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    Write-Host '[1/4] 创建虚拟环境...' -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host '[2/4] 安装依赖（清华镜像）...' -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q `
    -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

if (-not (Test-Path '.\.env')) {
    Copy-Item .env.example .env
    Write-Host '[3/4] 已生成 backend/.env' -ForegroundColor Cyan
}

Write-Host '[4/4] 执行迁移与种子数据...' -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m alembic upgrade head
& .\.venv\Scripts\python.exe -m app.db.seed

Write-Host '后端初始化完成。运行 .\scripts\start-backend.ps1 启动服务。' -ForegroundColor Green
