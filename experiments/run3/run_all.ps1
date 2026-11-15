# run3 overnight orchestrator (ASCII junction cwd)
$ErrorActionPreference = "Continue"
$RUN3 = "C:\Users\DMLAB\pilot_root\run3"
$ProgressLog = Join-Path $RUN3 "progress.log"
$Report = Join-Path $RUN3 "RUN3_REPORT.md"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
Set-Location $RUN3

function Write-Progress([string]$msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $line = "[$ts] $msg"
  Add-Content -Path $ProgressLog -Value $line -Encoding UTF8
  Write-Host $line
}

function Invoke-Step([string]$name, [string[]]$pyArgs) {
  Write-Progress "START $name :: python $($pyArgs -join ' ')"
  $t0 = Get-Date
  $allArgs = @("run", "-n", "pytorch", "--no-capture-output", "python") + $pyArgs
  & conda @allArgs
  $code = $LASTEXITCODE
  if ($null -eq $code) { $code = 0 }
  $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
  Write-Progress "END $name exit=$code elapsed_sec=$sec"
  return @{ name = $name; exit = $code; sec = $sec }
}

if (-not (Test-Path $ProgressLog)) {
  New-Item -ItemType File -Path $ProgressLog -Force | Out-Null
}
Write-Progress "=== run_all BEGIN pid=$PID ==="

$results = @()
$results += Invoke-Step "3-1_select" @("select_items.py")
$results += Invoke-Step "3-2_teacher" @("gen_teacher.py")
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$results += Invoke-Step "3-3_build_sft" @("build_sft.py")
$results += Invoke-Step "3-4_train" @("train_qlora.py", "--force")
$results += Invoke-Step "3-5_eval" @("gen_eval.py")
Write-Progress "=== run_all END ==="

function Count-Jsonl([string]$path) {
  if (-not (Test-Path $path)) { return "file_missing" }
  return @(Get-Content -Path $path -Encoding UTF8 | Where-Object { $_.Trim() -ne "" }).Count
}

$append = @()
$append += ""
$append += "## Bon silhaeng gyeolgwa (auto)"
$append += ""
$append += "- finished_at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$append += "- orchestrator_pid: $PID"
$append += ""
$append += "### step exit / sec"
$append += ""
$append += "| step | exit | sec |"
$append += "|---|---:|---:|"
foreach ($r in $results) {
  $append += "| $($r.name) | $($r.exit) | $($r.sec) |"
}
$append += ""
$append += "### artifact counts"
$append += ""
$append += "- items.jsonl: $(Count-Jsonl (Join-Path $RUN3 'items.jsonl'))"
$append += "- teacher_outputs.jsonl: $(Count-Jsonl (Join-Path $RUN3 'teacher_outputs.jsonl'))"
$append += "- sft_B.jsonl: $(Count-Jsonl (Join-Path $RUN3 'sft_B.jsonl'))"
$append += "- sft_C.jsonl: $(Count-Jsonl (Join-Path $RUN3 'sft_C.jsonl'))"
$append += "- eval_outputs.jsonl: $(Count-Jsonl (Join-Path $RUN3 'eval_outputs.jsonl'))"
$append += "- adapter_B: $(Test-Path (Join-Path $RUN3 'adapter_B\adapter_config.json'))"
$append += "- adapter_C: $(Test-Path (Join-Path $RUN3 'adapter_C\adapter_config.json'))"
$append += ""

$buildReport = Join-Path $RUN3 "build_sft_report.json"
if (Test-Path $buildReport) {
  $append += "### build_sft reason table"
  $append += ""
  $append += '```json'
  $append += (Get-Content $buildReport -Raw -Encoding UTF8)
  $append += '```'
  $append += ""
}

foreach ($side in @("B", "C")) {
  $loss = Join-Path $RUN3 "adapter_$side\train_log.jsonl"
  if (Test-Path $loss) {
    $append += "### train loss ($side)"
    $append += ""
    $append += '```'
    $append += ((Get-Content $loss -Encoding UTF8 | Select-Object -Last 40) -join "`n")
    $append += '```'
    $append += ""
  } else {
    $err = Join-Path $RUN3 "adapter_$side\ERROR.txt"
    if (Test-Path $err) {
      $append += "### train ERROR ($side)"
      $append += ""
      $append += '```'
      $append += (Get-Content $err -Raw -Encoding UTF8)
      $append += '```'
      $append += ""
    }
  }
}

# Korean section header for the report
$kor = @()
$kor += ""
$kor += "## 본 실행 결과 (자동 추가)"
$kor += ""
$kor += ($append -join "`n")
Add-Content -Path $Report -Value ($kor -join "`n") -Encoding UTF8
Write-Progress "appended results to RUN3_REPORT.md"
