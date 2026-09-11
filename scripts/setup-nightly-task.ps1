# PowerShell script to register Windows Task Scheduler job for Nightly Maintenance
# Paths derive from this script's own location ($PSScriptRoot = <vault>/scripts/),
# so the template registers the caller's own vault after clone (Release Plan Task 3).
$TaskName = "CodingVaultNightlyMaintenance"
$ScriptPath = Join-Path $PSScriptRoot "nightly-maintenance.py"
$VaultRoot = Split-Path -Parent $PSScriptRoot
$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "`"$ScriptPath`"" -WorkingDirectory $VaultRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily 3:00 AM Coding Vault memory compaction, quality audit, and cloud sync."
Write-Host "🎉 Successfully registered Windows Scheduled Task: $TaskName (Daily at 03:00 AM)" -ForegroundColor Green
