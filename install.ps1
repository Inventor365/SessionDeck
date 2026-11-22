# SessionDeck installer - creates Desktop + Start Menu shortcuts and adds the
# `sessiondeck` command to your PATH. Run via install.cmd (no admin needed).
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "`n== SessionDeck installer ==`n"

# 1. OpenSSH client
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Host "[!] OpenSSH client not found." -ForegroundColor Yellow
    Write-Host "    Install: Settings > System > Optional features > Add a feature > 'OpenSSH Client'"
    Write-Host "    (or, as admin: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0)`n"
} else { Write-Host "[ok] OpenSSH client" }

# 2. Windows Terminal (optional)
if (Get-Command wt -ErrorAction SilentlyContinue) { Write-Host "[ok] Windows Terminal" }
else { Write-Host "[i] Windows Terminal not found - sessions will open in plain console windows." -ForegroundColor Yellow
       Write-Host "    Recommended: winget install Microsoft.WindowsTerminal" }

# 3. Pick what to launch: the standalone exe if built, otherwise Python
$exe = Join-Path $dir "dist\SessionDeck.exe"
if (Test-Path $exe) {
    $target = $exe; $args = ""
    Write-Host "[ok] Using standalone $exe"
} else {
    $pyw = (Get-Command pyw -ErrorAction SilentlyContinue).Source
    if (-not $pyw) { $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }
    if (-not $pyw) {
        Write-Host "[X] Python 3 not found." -ForegroundColor Red
        Write-Host "    Install it with:  winget install Python.Python.3.13"
        Write-Host "    or from https://www.python.org/downloads/ (tick 'Add to PATH'), then run install again."
        Write-Host "    Alternatively download SessionDeck.exe from the Releases page (no Python needed)."
        exit 1
    }
    $py = $pyw -replace 'pythonw?\.exe$|pyw\.exe$', ''
    & ($pyw -replace 'w\.exe$', '.exe') -c "import tkinter" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "[X] Python found but tkinter is missing - reinstall Python with 'tcl/tk' enabled." -ForegroundColor Red; exit 1 }
    $target = $pyw; $args = "`"$dir\sessiondeck.pyw`""
    Write-Host "[ok] Python: $pyw"
}

# 4. Shortcuts
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) ""))
foreach ($p in $places) {
    $sc = $shell.CreateShortcut((Join-Path $p "SessionDeck.lnk"))
    $sc.TargetPath = $target; $sc.Arguments = $args; $sc.WorkingDirectory = $dir
    $sc.Description = "Manage persistent remote terminal sessions"
    if ($target -notlike "*.exe" -or $target -like "*pyw*") { $sc.IconLocation = "$env:SystemRoot\System32\imageres.dll,264" }
    $sc.Save()
}
Write-Host "[ok] Desktop and Start Menu shortcuts created"

# 5. PATH (for the `sessiondeck` command in cmd / PowerShell)
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ';') -notcontains $dir) {
    [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(';') + ";$dir").TrimStart(';')), "User")
    Write-Host "[ok] Added to PATH - open a new terminal to use 'sessiondeck'"
} else { Write-Host "[ok] Already on PATH" }

Write-Host "`nDone. Launch SessionDeck from the Desktop and click 'Servers...' to add your server.`n" -ForegroundColor Green
