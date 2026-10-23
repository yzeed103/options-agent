# Re-run every measurement on the consolidated SIP feed (own runtime_sip / reports\sip folders).
$ErrorActionPreference = "Continue"
$env:VZ_TAG = "sip"
Set-Location C:\project\options-agent
$s = "C:\Users\pc\AppData\Local\Temp\claude\C--project-quant\e36bb3a9-3f79-4bae-b32d-6857d633a8fd\scratchpad"
"== paper replay";   python tools/paper_replay.py --fresh 2>&1 | Select-Object -Last 2
"== learn + freeze"; python "$s\learn_first.py" 2>&1 | Select-Object -First 14
"== reports";        python "$s\reports_now.py" 2>&1 | Select-Object -First 3
"== eyes history";   python tools/eyes_history.py 2>&1 | Select-Object -Last 5
"== HAR test";       python tools/har_test.py 2>&1 | Select-Object -Last 5
"== trend";          python tools/trend_spectrum.py 2>&1 | Select-Object -Last 28
"== done"
