# run_paper_daily.ps1 -- daily paper-book driver for Task Scheduler (trigger 15:20 ET, weekdays).
#
# Runs one session pass against the IB paper account: calendar confirmation, exits and
# entries through the 15:45-15:55 ET order ladder, booking from fills, then refreshes the
# forward report. Safe by default:
#   - closed and early-close sessions skip before anything connects;
#   - if IB Gateway/TWS is not listening on a paper port, the skip is logged and the
#     task exits 0, so a gap in the book is explained rather than silent;
#   - orders are DRY-RUN unless the opt-in marker _private\TRANSMIT_OK exists, and a dry
#     pass writes only to outputs\live\dry;
#   - outputs\live\STOP blocks entries (exits still run); outputs\live\HALT stops all
#     transmission.
# Steps run as modules from the project root, so the package resolves without an
# install into the scheduled interpreter.
# Log: _private\logs\paper_daily_<date>.log

$ErrorActionPreference = "Continue"
# The project root is the parent of this script's folder, so the driver works from any clone.
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
$env:PYTHONIOENCODING = "utf-8"

$logDir = Join-Path $project "_private\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }
$log = Join-Path $logDir ("paper_daily_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Log($msg) { ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg) | Out-File $log -Append -Encoding utf8 }

# Task Scheduler fires on every weekday, holidays included. On a closed day an order
# would rest until the next open; on a 13:00 early close the ladder window is after the
# close. Both skip before anything connects, as on the cloud host.
py -m deploy.session_check *>> $log
$session = $LASTEXITCODE
if ($session -eq 10) { Log "Exchange closed today; nothing to do."; exit 0 }
if ($session -eq 11) { Log "Early close (13:00 ET); skipped. Positions due today exit on the next session."; exit 0 }
if ($session -ne 0) { Log "FAILED: session check errored (exit $session); no pass run."; exit 1 }

# paper ports only: 7497 = TWS paper, 4002 = Gateway paper
$port = $null
foreach ($p in 7497, 4002) {
    if ((Test-NetConnection -ComputerName 127.0.0.1 -Port $p -WarningAction SilentlyContinue).TcpTestSucceeded) {
        $port = $p; break
    }
}
if ($null -eq $port) {
    Log "SKIPPED: no IB paper gateway listening on 7497/4002. Book gap is explained, not silent."
    exit 0
}
Log "IB paper gateway found on port $port."
$env:IB_PORT = "$port"

$transmit = ""
if (Test-Path (Join-Path $project "_private\TRANSMIT_OK")) {
    $transmit = "--transmit"
    Log "TRANSMIT_OK marker present: orders will be transmitted to the PAPER account."
} else {
    Log "Dry-run mode (create _private\TRANSMIT_OK to transmit paper orders)."
}

Log "-- session pass --"
py -m scripts.paper_trade_ibkr session $transmit *>> $log
$status = $LASTEXITCODE
Log "session exit code: $status"

Log "-- forward report --"
py -m scripts.forward_report --out _private\reports\forward_report.md *>> $log
Log "report exit code: $LASTEXITCODE"

if (Select-String -Path $log -Pattern "ALARM:" -Quiet) {
    Log "ALARM raised during the pass (see above)."
    $status = 1
}
Log "done."
exit $status
