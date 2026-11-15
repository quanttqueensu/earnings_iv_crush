#!/usr/bin/env bash
# gateway_preflight.sh -- host-side check, run from cron before the daily pass.
#
# IB Gateway can lose its broker session overnight and stay up with the API port
# open (a refused reconnect leaves an IBC dialog on screen and nothing retries).
# Only the host can restart the gateway container, so this runs on the VM, not
# in the runner: probe the login, restart the gateway once if it is logged out,
# and re-probe until it recovers or the window runs out.
#
# Sends nothing to the broker beyond a read-only positions request. On failure it
# pings HEALTHCHECK_URL (from runner.env) with "/fail"; success stays silent so the
# daily pass remains the check's only success ping.
#
# Usage (on the VM, from cron at 15:00 ET on weekdays):
#     /opt/ivcrush/deploy/gateway_preflight.sh

set -uo pipefail
cd "$(dirname "$0")"

# state/control/logs/ is created by the runner container as root, so the host
# user writes beside it. An unwritable log must stop here: otherwise every probe
# redirect fails, reads as "logged out", and a healthy gateway gets restarted.
LOG=state/control/gateway_preflight.log
touch "$LOG" 2>/dev/null || { echo "gateway_preflight: cannot write $PWD/$LOG" >&2; exit 2; }

# IBC logs back in roughly 45 s after a restart on this host; 8 x 30 s leaves margin.
RETRIES=8
RETRY_WAIT_S=30

log() { printf '[%s] %s\n' "$(date +%T)" "$*" | tee -a "$LOG"; }

probe() {
    docker compose --profile run run --rm -T --entrypoint python runner \
        deploy/gateway_probe.py </dev/null >>"$LOG" 2>&1
}

ping_fail() {
    local url
    url=$(sed -n 's/^HEALTHCHECK_URL=//p' runner.env 2>/dev/null | tr -d '\r[:space:]')
    [ -n "$url" ] || return 0
    tail -n 40 "$LOG" | curl -fsS -m 15 --retry 3 --data-binary @- "${url}/fail" >/dev/null \
        || log "warning: health ping failed"
}

log "-- gateway preflight --"
probe
case $? in
    0) log "Gateway logged in; nothing to do."; exit 0 ;;
    3) log "FAILED: probe refused the endpoint (live port or non-paper account)."; ping_fail; exit 1 ;;
    *) log "Gateway not usable; restarting it." ;;
esac

docker compose restart ib-gateway </dev/null >>"$LOG" 2>&1
for i in $(seq 1 "$RETRIES"); do
    sleep "$RETRY_WAIT_S"
    if probe; then
        log "Gateway recovered after restart (probe $i)."
        exit 0
    fi
done

log "FAILED: gateway still not logged in $((RETRIES * RETRY_WAIT_S)) s after restart."
docker compose logs --tail 30 ib-gateway </dev/null 2>&1 | grep 'IBC:' | tail -10 >>"$LOG"
ping_fail
exit 1
