# Sequential resume download of Qwen2.5-14B-Instruct
$ErrorActionPreference = "Continue"
$Dest = "C:\Users\DMLAB\pilot_root\models\Qwen2.5-14B-Instruct"
$Log = "C:\Users\DMLAB\pilot_root\run3\hf_download_progress.log"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$base = "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct/resolve/main"
$files = @(
  @{ n = "config.json"; min = 100 },
  @{ n = "generation_config.json"; min = 50 },
  @{ n = "tokenizer.json"; min = 100000 },
  @{ n = "tokenizer_config.json"; min = 100 },
  @{ n = "vocab.json"; min = 100000 },
  @{ n = "merges.txt"; min = 1000 },
  @{ n = "model.safetensors.index.json"; min = 1000 },
  @{ n = "model-00001-of-00008.safetensors"; min = 3800000000 },
  @{ n = "model-00002-of-00008.safetensors"; min = 3900000000 },
  @{ n = "model-00003-of-00008.safetensors"; min = 3900000000 },
  @{ n = "model-00004-of-00008.safetensors"; min = 3900000000 },
  @{ n = "model-00005-of-00008.safetensors"; min = 3900000000 },
  @{ n = "model-00006-of-00008.safetensors"; min = 3900000000 },
  @{ n = "model-00007-of-00008.safetensors"; min = 3900000000 },
  @{ n = "model-00008-of-00008.safetensors"; min = 1600000000 }
)
function Write-Log($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Add-Content -Path $Log -Value $line -Encoding UTF8
  Write-Host $line
}
Write-Log "BEGIN dest=$Dest"
foreach ($item in $files) {
  $f = $item.n
  $out = Join-Path $Dest $f
  $cur = 0
  if (Test-Path $out) { $cur = (Get-Item $out).Length }
  if ($cur -ge $item.min) { Write-Log "skip ok $f size=$cur"; continue }
  Write-Log "GET $f have=$cur need>=$($item.min)"
  & curl.exe -L --fail --retry 10 --retry-delay 5 -C - --speed-time 60 --speed-limit 10000 -o $out "$base/$f"
  $code = $LASTEXITCODE
  $sz = 0
  if (Test-Path $out) { $sz = (Get-Item $out).Length }
  Write-Log "done exit=$code size=$sz $f"
  if ($sz -lt $item.min) { Write-Log "FAIL $f incomplete"; exit 1 }
}
Write-Log "DONE $Dest"
Set-Content -Path (Join-Path $Dest "DOWNLOAD_OK.txt") -Value (Get-Date -Format o) -Encoding UTF8
exit 0
