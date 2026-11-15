# Wait for base model download, finish smoke 3-4/3-5, archive smoke, start full run_all
$ErrorActionPreference = "Continue"
$RUN3 = "C:\Users\DMLAB\pilot_root\run3"
$SMOKE = Join-Path $RUN3 "smoke"
$Dest = "C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct"
$Marker = Join-Path $Dest "DOWNLOAD_OK.txt"
$Log = Join-Path $RUN3 "finish_smoke_and_run.log"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
Set-Location $RUN3

function Write-Log($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Add-Content -Path $Log -Value $line -Encoding UTF8
  Write-Host $line
}

Write-Log "BEGIN wait for $Marker"
$deadline = (Get-Date).AddHours(8)
while (-not (Test-Path $Marker)) {
  if ((Get-Date) -gt $deadline) { Write-Log "TIMEOUT waiting download"; exit 2 }
  $sz = 0
  Get-ChildItem (Join-Path $Dest "model-*.safetensors") -EA SilentlyContinue | ForEach-Object { $sz += $_.Length }
  Write-Log ("waiting download shards_GB={0:N2}" -f ($sz/1GB))
  Start-Sleep 60
}
Write-Log "download marker present"

# ensure SFT exists for smoke
conda run -n pytorch --no-capture-output python build_sft.py
$sftN = @(Get-Content (Join-Path $RUN3 "sft_B.jsonl") -EA SilentlyContinue | Where-Object Trim).Count
if ($sftN -lt 1) {
  Write-Log "force smoke sft"
  conda run -n pytorch --no-capture-output python force_smoke_sft.py
}

Write-Log "START smoke 3-4 train 5 steps"
$t0 = Get-Date
conda run -n pytorch --no-capture-output python train_qlora.py --max-steps 5 --force
$trainCode = $LASTEXITCODE
Write-Log "END smoke 3-4 exit=$trainCode sec=$([math]::Round(((Get-Date)-$t0).TotalSeconds,1))"

Write-Log "START smoke 3-5 eval 2"
$t0 = Get-Date
conda run -n pytorch --no-capture-output python gen_eval.py --limit 2
$evalCode = $LASTEXITCODE
Write-Log "END smoke 3-5 exit=$evalCode sec=$([math]::Round(((Get-Date)-$t0).TotalSeconds,1))"

# archive smoke artifacts (do not keep in run3 root)
New-Item -ItemType Directory -Force -Path $SMOKE | Out-Null
$moveList = @(
  "items.jsonl","teacher_outputs.jsonl","final_ids.txt","sft_B.jsonl","sft_C.jsonl",
  "build_sft_report.json","eval_outputs.jsonl","EVAL_COMPARE.md",
  "eval_outputs_A.jsonl","eval_outputs_B.jsonl","eval_outputs_C.jsonl",
  "nvidia_smi_after_teacher.txt","llama_server_teacher.log",
  "train_B_console.log","train_C_console.log",
  "gen_eval_A_console.log","gen_eval_B_console.log","gen_eval_C_console.log",
  "gen_eval_A_ERROR.txt","gen_eval_B_ERROR.txt","gen_eval_C_ERROR.txt",
  "_eval_items_all.json","_chk.txt"
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

$summary = [ordered]@{
  finished_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
  train_exit = $trainCode
  eval_exit = $evalCode
  smoke_dir = $SMOKE
}
$summary | ConvertTo-Json | Set-Content (Join-Path $RUN3 "smoke_summary.json") -Encoding UTF8
Write-Log ("SMOKE DONE " + ($summary | ConvertTo-Json -Compress))

# start full run_all (detached child would nest; run inline)
Write-Log "START full run_all"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RUN3 "run_all.ps1")
Write-Log "END full run_all exit=$LASTEXITCODE"
