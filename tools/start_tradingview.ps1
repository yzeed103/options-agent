# Starts TradingView Desktop with the local debug port the GEX agent uses (127.0.0.1:9222 only).
# If TradingView is already open WITHOUT the port, it is not closed for you: a message asks you to close it first.
$port = 9222
try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/json/version" -TimeoutSec 2 | Out-Null; exit 0 } catch {}
if (Get-Process -Name TradingView -ErrorAction SilentlyContinue) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("TradingView مفتوح بدون منفذ التحكم.`nأغلقه ثم افتح هذا الاختصار مرة ثانية حتى يقدر وكيل GEX يحدّث المستويات.", "TradingView GEX") | Out-Null
    exit 1
}
$loc = (Get-AppxPackage TradingView.Desktop).InstallLocation
Start-Process (Join-Path $loc 'TradingView.exe') -ArgumentList "--remote-debugging-port=$port", '--remote-allow-origins=http://127.0.0.1'
