# Runs the whole computer-use test and brings QGIS back after a crash. Started by RUN_EVERYTHING.bat; keep its window open.
#   1. the program-checked rows (no agent), 2. QGIS with the card dock, restarted up to 8 times while rows are still unfinished, 3. the report.
param([Parameter(Mandatory = $true)][string]$Pkg)
$ErrorActionPreference = "Continue"
$results = Join-Path $Pkg "results"
New-Item -ItemType Directory -Force -Path $results | Out-Null
$log = Join-Path $results "supervisor.log"
function Log($m) { $line = "$(Get-Date -Format s) $m"; Write-Host $line; Add-Content -Path $log -Value $line }

$qgis = @("C:\Program Files\QGIS 4.2.3") + @(Get-ChildItem "C:\Program Files" -Directory -Filter "QGIS*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) |
    Where-Object { Test-Path (Join-Path $_ "bin\qgis-bin.exe") } | Select-Object -First 1
if (-not $qgis) { Log "QGIS not found under C:\Program Files"; exit 2 }
Log "QGIS folder: $qgis"

function Unfinished {
    $cards = Get-Content (Join-Path $Pkg "cards.json") -Raw | ConvertFrom-Json
    $csv = Join-Path $results "RESULTS_GUI.csv"
    $done = @{}
    if (Test-Path $csv) { Import-Csv $csv | ForEach-Object { if ($_.evidence_error -eq "interrupted") { $done.Remove($_.row) } else { $done[$_.row] = $true } } }     # a row cut short by a crash is offered again (twice at most)
    return @($cards | Where-Object { $_.can_run -and -not $done.ContainsKey($_.id) })
}

if (-not (Test-Path (Join-Path $results "RESULTS.csv"))) {
    Log "running the program-checked rows"
    & (Join-Path $qgis "bin\python-qgis.bat") (Join-Path $Pkg "tools\run_smoke_headless.py") --out $results --plugin-src (Join-Path $Pkg "plugin") --rows-file (Join-Path $Pkg "docs\AGENT_RUN_ROWS.json") *> (Join-Path $results "headless.log")
    Log "program-checked rows finished, exit code $LASTEXITCODE (see results\headless.log, SUMMARY.md)"
}

$env:CARTOGEN_SMOKE_DIR = $Pkg
for ($i = 1; $i -le 8; $i++) {
    $left = Unfinished
    if ($left.Count -eq 0) { Log "every runnable row has a result"; break }
    Log "starting QGIS, attempt $i, rows left: $($left.Count)"
    $startLog = Join-Path $results "dock_start.log"
    $mark = 0
    if (Test-Path $startLog) { $mark = @(Get-Content $startLog).Count }
    $p = Start-Process -FilePath (Join-Path $qgis "bin\qgis-bin.exe") -ArgumentList @("--code", "`"$Pkg\tools\smoke_dock_start.py`"", "`"$Pkg\3_test_files\smoke_start.qgz`"") -PassThru -WindowStyle Maximized
    if (-not $p.WaitForExit(90000)) {
        $fresh = @(Get-Content $startLog -ErrorAction SilentlyContinue | Select-Object -Skip $mark)
        if (@($fresh | Where-Object { $_ -like "*dock shown*" }).Count -eq 0) { Log "WARNING: QGIS has run 90 s but the card dock did not report that it was shown; read results\dock_start.log and results\dock_errors.txt" } else { Log "the card dock reported that it was shown" }
        $p.WaitForExit()
    }
    Log "QGIS exited, code $($p.ExitCode)"
    Get-Process -Name "qgiscrashhandler" -ErrorAction SilentlyContinue | Stop-Process -Force      # the crash window would otherwise sit there and block the next start
    Start-Sleep -Seconds 5
}

Log "writing the report"
& (Join-Path $qgis "bin\python-qgis.bat") (Join-Path $Pkg "tools\analyze_smoke_run.py") $results (Join-Path $Pkg "cards.json") *> (Join-Path $results "analyze.log")
Log "done: open results\REPORT.md"
