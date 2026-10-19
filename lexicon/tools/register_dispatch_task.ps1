# Registers the dispatcher tick in Windows Task Scheduler (current user, no admin).
#   powershell -ExecutionPolicy Bypass -File lexicon\tools\register_dispatch_task.ps1
# Pause:  schtasks /change /tn EnglishCard_DispatchTick /disable   (resume: /enable)
# Remove: schtasks /delete /tn EnglishCard_DispatchTick /f
$ErrorActionPreference = 'Stop'
$name = 'EnglishCard_DispatchTick'
$root = Split-Path (Split-Path (Split-Path $PSCommandPath -Parent) -Parent) -Parent
$py = (Get-Command python.exe).Source
$pyw = Join-Path (Split-Path $py -Parent) 'pythonw.exe'
if (-not (Test-Path $pyw)) { throw "pythonw.exe not found next to $py" }
$script = Join-Path $root 'lexicon\tools\dispatch_tick.py'
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'english_card: board dispatcher tick every 2 min (owner 10/19: new cards start at once) (lexicon/tools/dispatch_tick.py, zero LLM tokens)' -Force | Out-Null
Get-ScheduledTask -TaskName $name | Select-Object TaskName, State
