# 一键启动全部：Docker 基础设施 + 后端 API + 前端页面
# 用法：在 PowerShell 里执行  E:\traexm\CRM\scripts\start-all.ps1
#       （或 cd E:\traexm\CRM 后执行 .\scripts\start-all.ps1）
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$logDir = Join-Path $env:TEMP 'crm-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Info($msg)  { Write-Host $msg -ForegroundColor Cyan }
function Ok($msg)    { Write-Host $msg -ForegroundColor Green }
function Warn($msg)  { Write-Host $msg -ForegroundColor Yellow }
function Fail($msg)  { Write-Host $msg -ForegroundColor Red }

# ---------------------------------------------------------------- 0) 前置检查
Info '[0/4] 前置检查...'

if (-not (Test-Path -LiteralPath $root)) {
    Fail "找不到工程目录：$root（外置盘可能没插好）"
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'docker-compose.yml'))) {
    Fail "工程目录不完整：$root\docker-compose.yml 不存在"
    exit 1
}
Ok "  工程目录：$root"

$py = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    Fail "  未找到后端虚拟环境：$py"
    Fail '  请先执行：.\scripts\init-backend.ps1'
    exit 1
}
Ok '  后端虚拟环境：OK'

# ---------------------------------------------------------------- 1) Docker 引擎
Info '[1/4] 等待 Docker 引擎就绪（开机后通常需要 30~60 秒）...'
$ready = $false
for ($i = 1; $i -le 36; $i++) {
    docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    if ($i -eq 1) {
        # 引擎没起来就先拉起 Docker Desktop（若已自启则无副作用）
        $desktop = 'D:\Docker\Docker Desktop.exe'
        if (Test-Path -LiteralPath $desktop) {
            Start-Process -FilePath $desktop -ErrorAction SilentlyContinue
            Warn '  Docker 引擎未运行，已尝试启动 Docker Desktop'
        }
    }
    Start-Sleep -Seconds 5
}
if (-not $ready) {
    Fail '  Docker 引擎 3 分钟仍未就绪，请手动打开 Docker Desktop 后重试'
    exit 1
}
Ok ("  引擎就绪：Docker " + (docker info --format '{{.ServerVersion}}'))

# ---------------------------------------------------------------- 2) 容器
Info '[2/4] 启动 PostgreSQL / Redis / MinIO...'
Set-Location $root
docker compose up -d | Out-Null
for ($i = 1; $i -le 24; $i++) {
    $health = docker compose ps --format '{{.Name}}|{{.Status}}'
    $unhealthy = @($health | Where-Object { $_ -notmatch '\(healthy\)' })
    if ($unhealthy.Count -eq 0 -and $health.Count -ge 3) { break }
    Start-Sleep -Seconds 3
}
docker compose ps --format 'table {{.Name}}\t{{.Status}}'

# ---------------------------------------------------------------- 3) 后端
function Test-Port($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# 清理残留的 uvicorn（尤其是用系统 Python 启动的野进程，会占住端口不放）
$strays = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*uvicorn*' })
if ($strays.Count -gt 0) {
    Warn ("  发现 {0} 个残留 uvicorn 进程，先清理" -f $strays.Count)
    foreach ($proc in $strays) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 3
}

Info '[3/4] 启动后端 API（http://localhost:8000/docs）...'
Start-Process -FilePath $py `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000' `
    -WorkingDirectory (Join-Path $root 'backend') `
    -RedirectStandardOutput (Join-Path $logDir 'uvicorn.log') `
    -RedirectStandardError (Join-Path $logDir 'uvicorn.err.log') `
    -WindowStyle Hidden

# ---------------------------------------------------------------- 4) 前端
if (Test-Port 3000) {
    Warn '[4/4] 端口 3000 已被占用，尝试复用'
} else {
    Info '[4/4] 启动前端（http://localhost:3000）...'
    $dist = Join-Path $root 'frontend\.next'
    if (-not (Test-Path -LiteralPath $dist)) {
        Warn '  未找到前端构建产物，先执行 npm run build（首次较慢）...'
        Start-Process -FilePath 'C:\Program Files\nodejs\npm.cmd' -ArgumentList 'run', 'build' `
            -WorkingDirectory (Join-Path $root 'frontend') -Wait -NoNewWindow
    }
    Start-Process -FilePath 'C:\Program Files\nodejs\npm.cmd' `
        -ArgumentList 'run', 'start' `
        -WorkingDirectory (Join-Path $root 'frontend') `
        -RedirectStandardOutput (Join-Path $logDir 'next.log') `
        -RedirectStandardError (Join-Path $logDir 'next.err.log') `
        -WindowStyle Hidden
}

Start-Sleep -Seconds 12

# ---------------------------------------------------------------- 健康检查
Write-Host ''
Info '--- 健康检查 ---'
$backendOk = $false
try {
    $h = (Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 15).data
    Ok ("后端   : ok  (postgres={0}, redis={1})" -f $h.postgres, $h.redis)
    $backendOk = $true
} catch {
    Fail '后端   : 无响应，查看日志 ' + (Join-Path $logDir 'uvicorn.err.log')
}
try {
    $code = (Invoke-WebRequest 'http://127.0.0.1:3000/login' -UseBasicParsing -TimeoutSec 15).StatusCode
    Ok ("前端   : HTTP {0}" -f $code)
} catch {
    Fail '前端   : 无响应，查看日志 ' + (Join-Path $logDir 'next.err.log')
}

Write-Host ''
if ($backendOk) {
    Ok '访问 http://localhost:3000   演示账号 admin / admin123'
} else {
    Warn '服务未完全就绪，请查看上面提示的日志文件'
}
Write-Host ("日志目录：{0}" -f $logDir) -ForegroundColor DarkGray
