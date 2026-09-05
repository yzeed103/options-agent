#Requires -Version 5.1
<#
.SYNOPSIS
    Detects and disables automatic backup mechanisms that write to a given drive.

.DESCRIPTION
    Scans Windows for every common source of automatic backups (File History,
    Windows Backup, Volume Shadow Copies, OneDrive folder backup, third-party
    backup services, scheduled tasks and startup entries), reports what it
    finds, and optionally disables them.

    Runs in report-only mode by default. Nothing is changed unless -Apply is
    passed. A transcript of the scan is written next to this script.

.PARAMETER Drive
    Drive letter to investigate. Default: D:

.PARAMETER Apply
    Actually disable what was found. Without it, the script only reports.

.PARAMETER IncludeThirdParty
    Also stop and disable non-Microsoft backup services. Off by default because
    it touches software the script did not install.

.PARAMETER DeleteShadowCopies
    Permanently delete existing shadow copies (restore points) on the drive.
    Off by default and irreversible.

.EXAMPLE
    .\disable_auto_backup.ps1
    Report only. Shows what is writing to D: without changing anything.

.EXAMPLE
    .\disable_auto_backup.ps1 -Apply -IncludeThirdParty
    Disable Microsoft and third-party automatic backups targeting D:.
#>
[CmdletBinding()]
param(
    [string] $Drive = 'D:',
    [switch] $Apply,
    [switch] $IncludeThirdParty,
    [switch] $DeleteShadowCopies
)

$ErrorActionPreference = 'Continue'
$Drive = $Drive.TrimEnd('\')
if ($Drive -notmatch '^[A-Za-z]:$') { throw "Drive must look like 'D:' - got '$Drive'" }

$script:Findings = @()
$script:Changes  = @()

function Write-Section {
    param([string] $Title)
    Write-Host ''
    Write-Host ('=' * 68) -ForegroundColor DarkCyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ('=' * 68) -ForegroundColor DarkCyan
}

function Write-Found { param([string] $Text) Write-Host "  [FOUND]  $Text" -ForegroundColor Yellow }
function Write-Done  { param([string] $Text) Write-Host "  [DONE]   $Text" -ForegroundColor Green  }
function Write-Skip  { param([string] $Text) Write-Host "  [SKIP]   $Text" -ForegroundColor DarkGray }
function Write-Clean { param([string] $Text) Write-Host "  [CLEAN]  $Text" -ForegroundColor DarkGreen }
function Write-Warn2 { param([string] $Text) Write-Host "  [WARN]   $Text" -ForegroundColor Red }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Folder names that mean "something is backing up here".
$BackupFolderPatterns = @(
    'FileHistory', 'WindowsImageBackup', 'MSSQL.*Backup', 'Backup', 'Backups',
    'Acronis', 'Macrium', 'Reflect', 'EaseUS', 'Veeam', 'AOMEI', 'Paragon',
    'Cobian', 'Duplicati', 'SyncBack', 'GoodSync', 'FreeFileSync', 'Carbonite',
    'IDrive', 'CrashPlan', 'Backblaze', 'Time Machine', 'OneDrive', 'Dropbox',
    'Google Drive', 'MEGAsync', 'pCloud', 'Yandex', 'Nextcloud'
)
$BackupKeyword = 'backup|filehistory|shadow|restore ?point|acronis|macrium|easeus|veeam|aomei|paragon|cobian|duplicati|syncback|goodsync|freefilesync|carbonite|idrive|crashplan|backblaze|megasync|pcloud|nextcloud|yandex ?disk'

$baseDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$transcript = Join-Path $baseDir 'backup-scan-report.txt'
try { Start-Transcript -Path $transcript -Force | Out-Null } catch { }

Write-Host ''
Write-Host "  Auto-backup killer - target drive: $Drive" -ForegroundColor White
Write-Host "  Mode: $(if ($Apply) { 'APPLY (changes will be made)' } else { 'REPORT ONLY (nothing is changed)' })" -ForegroundColor White
Write-Host "  Admin: $(if (Test-Admin) { 'yes' } else { 'NO - rerun as Administrator to change anything' })" -ForegroundColor White

if ($Apply -and -not (Test-Admin)) {
    Write-Warn2 'Cannot apply changes without Administrator rights. Right-click PowerShell -> Run as administrator.'
    try { Stop-Transcript | Out-Null } catch { }
    return
}

# ---------------------------------------------------------------- 1. the drive
Write-Section "1. What lives on $Drive"

if (-not (Test-Path "$Drive\")) {
    Write-Warn2 "Drive $Drive is not present on this machine. Nothing to scan there."
} else {
    $items = Get-ChildItem "$Drive\" -Force -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending
    if (-not $items) {
        Write-Clean "Drive $Drive is empty."
    } else {
        $items | Select-Object -First 25 |
            Format-Table @{ n = 'Name'; e = { $_.Name }; w = 40 },
                         @{ n = 'Last written'; e = { $_.LastWriteTime }; w = 22 },
                         @{ n = 'Type'; e = { if ($_.PSIsContainer) { 'folder' } else { 'file' } } } |
            Out-String | Write-Host

        foreach ($it in $items) {
            foreach ($p in $BackupFolderPatterns) {
                if ($it.Name -match $p) {
                    Write-Found "$($it.Name)  ->  looks like backup data (last written $($it.LastWriteTime))"
                    $script:Findings += "Folder $Drive\$($it.Name)"
                    break
                }
            }
        }
    }
}

# ------------------------------------------------------- 2. File History
Write-Section '2. File History'

$fh = Get-Service -Name 'fhsvc' -ErrorAction SilentlyContinue
if ($fh) {
    if ($fh.Status -eq 'Running' -or $fh.StartType -ne 'Disabled') {
        Write-Found "Service fhsvc (File History) - status $($fh.Status), startup $($fh.StartType)"
        $script:Findings += 'File History service'
        if ($Apply) {
            Stop-Service 'fhsvc' -Force -ErrorAction SilentlyContinue
            Set-Service  'fhsvc' -StartupType Disabled -ErrorAction SilentlyContinue
            Write-Done 'File History service stopped and disabled.'
            $script:Changes += 'Disabled service fhsvc'
        }
    } else {
        Write-Clean 'File History service already stopped and disabled.'
    }
} else {
    Write-Clean 'File History service not present.'
}

# Its registry switch, so the Settings UI agrees with us.
$fhKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\FileHistory'
if ($Apply) {
    if (-not (Test-Path $fhKey)) { New-Item -Path $fhKey -Force | Out-Null }
    New-ItemProperty -Path $fhKey -Name 'Disabled' -Value 1 -PropertyType DWord -Force | Out-Null
    Write-Done 'File History disabled by policy (HKLM policy key set).'
    $script:Changes += 'Set FileHistory policy Disabled=1'
}

# --------------------------------------------------- 3. Windows Backup
Write-Section '3. Windows Backup (built-in imaging)'

foreach ($svcName in @('SDRSVC', 'wbengine')) {
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if (-not $svc) { Write-Clean "Service $svcName not present."; continue }

    if ($svc.Status -eq 'Running' -or $svc.StartType -eq 'Automatic') {
        Write-Found "Service $svcName ($($svc.DisplayName)) - status $($svc.Status), startup $($svc.StartType)"
        $script:Findings += "Service $svcName"
        if ($Apply) {
            Stop-Service $svcName -Force -ErrorAction SilentlyContinue
            Set-Service  $svcName -StartupType Disabled -ErrorAction SilentlyContinue
            Write-Done "$svcName stopped and disabled."
            $script:Changes += "Disabled service $svcName"
        }
    } else {
        Write-Clean "Service $svcName is not running automatically (startup $($svc.StartType))."
    }
}

# ------------------------------------------- 4. Scheduled tasks
Write-Section '4. Scheduled tasks'

$tasks = Get-ScheduledTask -ErrorAction SilentlyContinue
$hits  = @()

foreach ($t in $tasks) {
    if ($t.State -eq 'Disabled') { continue }

    $nameHit = ($t.TaskName -match $BackupKeyword) -or ($t.TaskPath -match $BackupKeyword)

    $driveHit = $false
    foreach ($a in $t.Actions) {
        $blob = "$($a.Execute) $($a.Arguments) $($a.WorkingDirectory)"
        if ($blob -like "*$Drive\*") { $driveHit = $true; break }
    }

    if ($nameHit -or $driveHit) {
        $hits += [pscustomobject]@{
            Task    = $t.TaskName
            Path    = $t.TaskPath
            State   = $t.State
            Why     = if ($driveHit) { "writes to $Drive" } else { 'backup-related name' }
            Object  = $t
        }
    }
}

if (-not $hits) {
    Write-Clean 'No enabled scheduled task looks backup-related or targets the drive.'
} else {
    $hits | Format-Table Task, Path, State, Why -AutoSize | Out-String | Write-Host
    foreach ($h in $hits) {
        Write-Found "$($h.Path)$($h.Task)  ($($h.Why))"
        $script:Findings += "Task $($h.Path)$($h.Task)"
        if ($Apply) {
            try {
                Disable-ScheduledTask -TaskName $h.Object.TaskName -TaskPath $h.Object.TaskPath -ErrorAction Stop | Out-Null
                Write-Done "Disabled task $($h.Path)$($h.Task)"
                $script:Changes += "Disabled task $($h.Path)$($h.Task)"
            } catch {
                Write-Warn2 "Could not disable $($h.Path)$($h.Task): $($_.Exception.Message)"
            }
        }
    }
}

# ------------------------------------ 5. Third-party backup services
Write-Section '5. Third-party backup software'

$thirdParty = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object {
    $_.PathName -and
    $_.PathName -notmatch '(?i)\\Windows\\' -and
    ("$($_.Name) $($_.DisplayName) $($_.PathName)" -match "(?i)$BackupKeyword")
}

if (-not $thirdParty) {
    Write-Clean 'No third-party backup service detected.'
} else {
    foreach ($s in $thirdParty) {
        Write-Found "$($s.Name)  -  $($s.DisplayName)  [$($s.State), $($s.StartMode)]"
        Write-Host  "           $($s.PathName)" -ForegroundColor DarkGray
        $script:Findings += "Third-party service $($s.Name)"

        if ($Apply -and $IncludeThirdParty) {
            Stop-Service  $s.Name -Force -ErrorAction SilentlyContinue
            Set-Service   $s.Name -StartupType Disabled -ErrorAction SilentlyContinue
            Write-Done "Stopped and disabled $($s.Name)."
            $script:Changes += "Disabled third-party service $($s.Name)"
        } elseif ($Apply) {
            Write-Skip "Left alone. Rerun with -IncludeThirdParty to disable it."
        }
    }
    Write-Host ''
    Write-Host '  NOTE: disabling the service stops the schedule, but the program stays installed.' -ForegroundColor DarkGray
    Write-Host '        To remove it for good: Settings > Apps > Installed apps > uninstall it.'   -ForegroundColor DarkGray
}

# --------------------------------- 6. Startup entries
Write-Section '6. Startup entries'

$runKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
)
$startupHit = $false
foreach ($k in $runKeys) {
    if (-not (Test-Path $k)) { continue }
    $props = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
    foreach ($p in $props.PSObject.Properties) {
        if ($p.Name -like 'PS*') { continue }
        if ("$($p.Name) $($p.Value)" -match "(?i)$BackupKeyword") {
            $startupHit = $true
            Write-Found "$k :: $($p.Name) = $($p.Value)"
            $script:Findings += "Startup entry $($p.Name)"
        }
    }
}
if (-not $startupHit) { Write-Clean 'No backup-related startup entry found.' }
Write-Host '  (Startup entries are left in place. Remove them from Task Manager > Startup apps.)' -ForegroundColor DarkGray

# --------------------------- 7. Shadow copies / System Protection
Write-Section "7. System Protection and shadow copies on $Drive"

$shadow = & vssadmin list shadows /for=$Drive 2>&1 | Out-String
$count  = ([regex]::Matches($shadow, 'Shadow Copy ID')).Count

if ($shadow -match '(?i)requires administrator|denied|مرفوض') {
    Write-Skip 'Shadow copies could not be listed without Administrator rights.'
} elseif ($count -eq 0) {
    Write-Clean "No shadow copies stored on $Drive."
} else {
    Write-Found "$count shadow copy/copies stored on $Drive."
    $script:Findings += "$count shadow copies on $Drive"
}

if ($Apply) {
    try {
        Disable-ComputerRestore -Drive "$Drive\" -ErrorAction Stop
        Write-Done "System Protection turned off for $Drive."
        $script:Changes += "Disabled System Restore on $Drive"
    } catch {
        Write-Skip "System Protection was not enabled for $Drive (nothing to turn off)."
    }

    if ($DeleteShadowCopies) {
        & vssadmin delete shadows /for=$Drive /all /quiet 2>&1 | Out-String | Write-Host
        Write-Done "Existing shadow copies on $Drive deleted."
        $script:Changes += "Deleted shadow copies on $Drive"
    } else {
        Write-Skip 'Existing shadow copies kept. Pass -DeleteShadowCopies to erase them (irreversible).'
    }
}

# ------------------------------------------- 8. Cloud sync
Write-Section '8. Cloud folder backup (OneDrive and friends)'

$od = Get-Process -Name 'OneDrive' -ErrorAction SilentlyContinue
if ($od) {
    Write-Found 'OneDrive is running. It may be syncing folders to the cloud.'
    $script:Findings += 'OneDrive running'
} else {
    Write-Clean 'OneDrive is not running.'
}
Write-Host '  Cloud sync cannot be switched off safely from a script.' -ForegroundColor DarkGray
Write-Host '  Do it by hand: OneDrive icon > Settings > Sync and backup > Manage backup > turn all off.' -ForegroundColor DarkGray

# ------------------------------------------------------------- summary
Write-Section 'Summary'

if (-not $script:Findings) {
    Write-Host '  Nothing is automatically backing up to this drive. You are already clean.' -ForegroundColor Green
} else {
    Write-Host "  Found $($script:Findings.Count) item(s):" -ForegroundColor Yellow
    $script:Findings | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}

if ($Apply) {
    Write-Host ''
    if ($script:Changes) {
        Write-Host "  Applied $($script:Changes.Count) change(s):" -ForegroundColor Green
        $script:Changes | ForEach-Object { Write-Host "    - $_" -ForegroundColor Green }
        Write-Host ''
        Write-Host '  Restart the computer, then run this script again with no arguments to verify.' -ForegroundColor White
    } else {
        Write-Host '  No changes were necessary.' -ForegroundColor Green
    }
} else {
    Write-Host ''
    Write-Host '  This was a report only. Nothing was changed.' -ForegroundColor White
    Write-Host '  To actually disable everything above, run as Administrator:' -ForegroundColor White
    Write-Host "      .\disable_auto_backup.ps1 -Drive $Drive -Apply -IncludeThirdParty" -ForegroundColor White
}

Write-Host ''
Write-Host '  How to undo any of this later:' -ForegroundColor DarkGray
Write-Host '    Set-Service fhsvc  -StartupType Manual   ; Start-Service fhsvc'   -ForegroundColor DarkGray
Write-Host '    Set-Service SDRSVC -StartupType Manual   ; Start-Service SDRSVC'  -ForegroundColor DarkGray
Write-Host '    Enable-ScheduledTask -TaskPath <path> -TaskName <name>'           -ForegroundColor DarkGray
Write-Host "    Enable-ComputerRestore -Drive '$Drive\'"                          -ForegroundColor DarkGray
Write-Host ''
Write-Host "  Full report saved to: $transcript" -ForegroundColor DarkGray
Write-Host ''

try { Stop-Transcript | Out-Null } catch { }
