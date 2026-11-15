#Requires -RunAsAdministrator
# GPU crash mitigations. Run in Admin PowerShell, then reboot.
# UTF-8 BOM recommended. This file uses ASCII-only messages.

$ErrorActionPreference = "Continue"
Write-Host "=== ADMIN GPU mitigations ===" -ForegroundColor Cyan

# 1) TDR delay
$tdrPath = "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
New-ItemProperty -Path $tdrPath -Name "TdrDelay" -PropertyType DWord -Value 60 -Force | Out-Null
New-ItemProperty -Path $tdrPath -Name "TdrDdiDelay" -PropertyType DWord -Value 60 -Force | Out-Null
Write-Host "TDR Delay/DdiDelay = 60s OK"

# 2) Hardware-accelerated GPU scheduling off (HwSchMode=1)
$sch = "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
try {
  New-ItemProperty -Path $sch -Name "HwSchMode" -PropertyType DWord -Value 1 -Force | Out-Null
  Write-Host "HwSchMode=1 (HAGS off) OK"
} catch {
  Write-Host "HwSchMode skip: $_"
}

# 3) GPU power limit (TITAN RTX)
foreach ($i in 0,1) {
  & nvidia-smi -i $i -pl 220
  Write-Host ("power limit GPU{0} -> 220W (rc={1})" -f $i, $LASTEXITCODE)
}

# 4) Sleep / hibernate
powercfg /hibernate off 2>$null
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP 0
powercfg /SETACTIVE SCHEME_CURRENT
Write-Host "powercfg hibernate/sleep OK"

Write-Host ""
Write-Host "DONE. Reboot now so TDR/HAGS fully apply." -ForegroundColor Green
Write-Host "After reboot: nvidia-smi, then run resume_32b_robust.py"
pause
