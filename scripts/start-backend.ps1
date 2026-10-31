# 启动后端 API（http://localhost:8000/docs）
$backend = Join-Path $PSScriptRoot '..\backend'
Set-Location $backend
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
