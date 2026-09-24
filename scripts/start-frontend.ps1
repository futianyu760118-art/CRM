# 启动前端（http://localhost:3000）
$frontend = Join-Path $PSScriptRoot '..\frontend'
Set-Location $frontend
npm run dev
