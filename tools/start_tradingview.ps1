# Starts TradingView Desktop with the local debug port the GEX agent uses (127.0.0.1:9222 only).
# -AtLogon (the TradingViewGEX task): if TradingView was just opened WITHOUT the port at boot (its own "start with
#   Windows" option, or Windows restoring apps), it is closed and reopened with the port - nothing is open in it yet.
# Otherwise a TradingView already open without the port is never closed: a message asks you to close it first.
# Keep this file saved as UTF-8 WITH BOM: Windows PowerShell 5.1 misreads the Arabic text without it.
param([switch]$AtLogon)
$port = 9222
function PortOpen { try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/json/version" -TimeoutSec 2 | Out-Null; $true } catch { $false } }
if (PortOpen) { exit 0 }
$tv = Get-Process -Name TradingView -ErrorAction SilentlyContinue
if ($tv) {
    $age = (Get-Date) - ($tv | Sort-Object StartTime | Select-Object -First 1).StartTime
    if ($AtLogon -and $age.TotalMinutes -lt 3) {
        $tv | ForEach-Object { $_.CloseMainWindow() | Out-Null }
        Start-Sleep -Seconds 8
        Get-Process -Name TradingView -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 2
    } else {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("TradingView مفتوح بدون منفذ التحكم.`nأغلقه ثم افتح اختصار TradingView GEX حتى يقدر وكيل GEX يحدّث المستويات.", "TradingView GEX") | Out-Null
        exit 1
    }
}
$loc = (Get-AppxPackage TradingView.Desktop).InstallLocation
Start-Process (Join-Path $loc 'TradingView.exe') -ArgumentList "--remote-debugging-port=$port", '--remote-allow-origins=http://127.0.0.1'
