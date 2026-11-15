# Smoke test for run3 pipeline (ASCII junction cwd)
$ErrorActionPreference = "Continue"
$RUN3 = "C:\Users\DMLAB\pilot_root\run3"
$SMOKE = Join-Path $RUN3 "smoke"
$Summary = Join-Path $RUN3 "smoke_summary.json"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
Set-Location $RUN3

function Step([string]$name, [scriptblock]$block) {
  $t0 = Get-Date
  Write-Host "==== START $name $($t0.ToString('HH:mm:ss')) ===="
  $code = 0
  $err = ""
  try {
    & $block
    if ($null -ne $LASTEXITCODE) { $code = $LASTEXITCODE }
  } catch {
    $code = 1
    $err = "$_"
    Write-Host $err
  }
  $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
  Write-Host "==== END $name exit=$code sec=$sec ===="
  return [pscustomobject]@{ name = $name; exit = $code; sec = $sec; err = $err }
}

$results = @()

@(
  "items.jsonl","teacher_outputs.jsonl","final_ids.txt","sft_B.jsonl","sft_C.jsonl",
  "build_sft_report.json","eval_outputs.jsonl","EVAL_COMPARE.md",
  "eval_outputs_A.jsonl","eval_outputs_B.jsonl","eval_outputs_C.jsonl",
  "nvidia_smi_after_teacher.txt"
) | ForEach-Object { Remove-Item (Join-Path $RUN3 $_) -Force -ErrorAction SilentlyContinue }
Remove-Item (Join-Path $RUN3 "adapter_B") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $RUN3 "adapter_C") -Recurse -Force -ErrorAction SilentlyContinue
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force

$results += Step "3-1_select" { conda run -n pytorch --no-capture-output python select_items.py }
$results += Step "3-2_teacher_3" { conda run -n pytorch --no-capture-output python gen_teacher.py --limit 3 }
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
$results += Step "3-3_build_sft" { conda run -n pytorch --no-capture-output python build_sft.py }

$sftB = Join-Path $RUN3 "sft_B.jsonl"
$sftN = 0
if (Test-Path $sftB) { $sftN = @(Get-Content $sftB -Encoding UTF8 | Where-Object { $_.Trim() }).Count }
$forced = $false
if ($sftN -lt 1) {
  Write-Host "WARN: sft empty after 3-3; forcing smoke SFT from teacher_outputs"
  conda run -n pytorch --no-capture-output python force_smoke_sft.py
  $forced = $true
}

$results += Step "3-4_train_5steps" { conda run -n pytorch --no-capture-output python train_qlora.py --max-steps 5 --force }
$results += Step "3-5_eval_2" { conda run -n pytorch --no-capture-output python gen_eval.py --limit 2 }

New-Item -ItemType Directory -Force -Path $SMOKE | Out-Null
$moveList = @(
  "items.jsonl","teacher_outputs.jsonl","final_ids.txt","sft_B.jsonl","sft_C.jsonl",
  "build_sft_report.json","eval_outputs.jsonl","EVAL_COMPARE.md",
  "eval_outputs_A.jsonl","eval_outputs_B.jsonl","eval_outputs_C.jsonl",
  "nvidia_smi_after_teacher.txt","llama_server_teacher.log",
  "train_B_console.log","train_C_console.log",
  "gen_eval_A_console.log","gen_eval_B_console.log","gen_eval_C_console.log",
  "gen_eval_A_ERROR.txt","gen_eval_B_ERROR.txt","gen_eval_C_ERROR.txt"
)
foreach ($f in $moveList) {
  $src = Join-Path $RUN3 $f
  if (Test-Path $src) { Move-Item -Force $src (Join-Path $SMOKE $f) }
}
foreach ($d in @("adapter_B","adapter_C")) {
  $src = Join-Path $RUN3 $d
  if (Test-Path $src) {
    $dst = Join-Path $SMOKE $d
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Move-Item -Force $src $dst
  }
}

$obj = [ordered]@{
  finished_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
  forced_sft_for_train_smoke = $forced
  steps = $results
  smoke_dir = $SMOKE
}
$obj | ConvertTo-Json -Depth 6 | Set-Content -Path $Summary -Encoding UTF8
Write-Host "SMOKE DONE summary=$Summary"
$obj | ConvertTo-Json -Depth 6
