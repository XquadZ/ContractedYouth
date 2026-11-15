# 실험/학습 백그라운드 실행
# 예: .\pilot\run_bg.ps1 -Script .\pilot\teacher_compare.py -LogName teacher_compare
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string]$LogName = "run",
    [string]$Root = "C:\Users\DMLAB\Desktop\학부-AI서비스 개발"
)

$ErrorActionPreference = "Stop"
Set-Location $Root
New-Item -ItemType Directory -Force -Path ".\pilot\runs" | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $Root "pilot\runs\${LogName}_${stamp}.log"
$latest = Join-Path $Root "pilot\runs\${LogName}_latest.log"

$inner = @"
`$env:PYTHONIOENCODING='utf-8'
`$env:PYTHONUNBUFFERED='1'
Set-Location -LiteralPath '$Root'
python -u '$Script' *> '$latest'
Copy-Item -Force '$latest' '$log'
exit `$LASTEXITCODE
"@

$p = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $inner) `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru

"pid=$($p.Id)"
"log=$latest"
"archive=$log"
"watch=Get-Content -LiteralPath `"$latest`" -Wait -Tail 40 -Encoding utf8"
