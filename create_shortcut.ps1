# Creates a NetBridge shortcut on the Desktop: NetBridge icon, no console window.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw  = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) { Write-Host "pythonw.exe not found. Install Python and tick 'Add to PATH'."; exit 1 }
$desktop = [Environment]::GetFolderPath("Desktop")
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop "NetBridge.lnk"))
$lnk.TargetPath       = $pyw
$lnk.Arguments        = "`"$root\main.py`""
$lnk.WorkingDirectory = $root
$lnk.IconLocation     = "$root\assets\netbridge.ico,0"
$lnk.Description      = "NetBridge"
$lnk.Save()
Write-Host "Shortcut created on the Desktop."
