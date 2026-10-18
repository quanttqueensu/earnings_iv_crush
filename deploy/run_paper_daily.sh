#!/usr/bin/env bash
# run_paper_daily.sh -- daily forward paper-book pass inside the runner container.
#
# Linux twin of scripts/run_paper_daily.ps1, with two deliberate differences for
# an unattended host:
#   - a missing gateway is a FAILURE here, not a skip. On a laptop it usually
#     means the machine was off; on an always-on VM it means the login broke,
#     and a green run that traded nothing would hide that for weeks.
#   - closed and early-close sessions skip before anything connects, so no order
#     is ever queued against a book the pass did not see.
#
# Orders are DRY-RUN unless /app/control/TRANSMIT_OK exists. Even then they go to
# the paper account only: the harness refuses every live port.
#
# Optional env: HEALTHCHECK_URL (healthchecks.io-style ping URL; "/fail" is
# appended on failure).

set -uo pipefail
cd /app

CONTROL=/app/control
LOGDIR="$CONTROL/logs"
mkdir -p "$LOGDIR" "$CONTROL/reports"
LOG="$LOGDIR/paper_daily_$(date +%F).log"

log() { printf '[%s] %s\n' "$(date +%T)" "$*" | tee -a "$LOG"; }

ping_monitor() {
    # $1: "" for success, "/fail" for failure. The log tail rides along so the
    # alert email says what broke.
    [ -n "${HEALTHCHECK_URL:-}" ] || return 0
    tail -n 40 "$LOG" | curl -fsS -m 15 --retry 3 --data-binary @- \
        "${HEALTHCHECK_URL}$1" >/dev/null || log "warning: health ping failed"
}

fail() { log "FAILED: $*"; ping_monitor /fail; exit 1; }

log "-- session check --"
python deploy/session_check.py >>"$LOG" 2>&1
case $? in
    0) ;;
    10) log "Exchange closed today; nothing to do."; ping_monitor ""; exit 0 ;;
    11) log "Early close (13:00 ET); the ladder window is after the close. Skipped;" \
            "positions due today exit on the next session."; ping_monitor ""; exit 0 ;;
    *) fail "session check errored" ;;
esac

log "-- gateway check (${IB_HOST}:${IB_PORT}) --"
# The gateway restarts nightly and may still be logging in after a reboot, so
# allow it a few minutes before calling the login broken.
ready=0
for _ in $(seq 1 12); do
    if python - <<'PY'
import os, socket, sys
try:
    socket.create_connection((os.environ["IB_HOST"], int(os.environ["IB_PORT"])), 5).close()
except OSError:
    sys.exit(1)
PY
    then ready=1; break; fi
    sleep 15
done
[ "$ready" = 1 ] || fail "no IB paper gateway on ${IB_HOST}:${IB_PORT} after 3 minutes"
log "Gateway reachable."

transmit=""
if [ -f "$CONTROL/TRANSMIT_OK" ]; then
    transmit="--transmit"
    log "TRANSMIT_OK present: orders will be transmitted to the PAPER account."
else
    log "Dry-run mode (touch $CONTROL/TRANSMIT_OK to transmit paper orders)."
fi

status=0

# One pass: exits and entries run through the same 15:45-15:55 ET ladder, so the
# pass must start by 15:20 to leave time for calendar confirmation and snapshots.
log "-- session pass --"
python -m scripts.paper_trade_ibkr session $transmit >>"$LOG" 2>&1 \
    || { log "session exit $?"; status=1; }

log "-- significance report --"
python scripts/forward_report.py --out "$CONTROL/reports/forward_report.md" >>"$LOG" 2>&1 \
    || { log "report exit $?"; status=1; }

# An entry pass where candidates were seen and none priced is a data fault the
# harness flags with ALARM while still exiting 0; surface it as a failure.
if grep -q "ALARM:" "$LOG"; then
    log "ALARM raised during the pass (see above)."
    status=1
fi

[ "$status" = 0 ] || fail "one or more steps failed"
log "done."
ping_monitor ""
