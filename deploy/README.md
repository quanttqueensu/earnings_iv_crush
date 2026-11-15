# Cloud forward paper book

Runs the IBKR forward paper book unattended on an always-on VM: IB Gateway stays
logged into the paper account in one container, and a one-shot runner container
executes the daily session pass (calendar, exits and entries through the 15:45-15:55 ET ladder,
then the forward report) from 15:20 ET on
NYSE sessions. Nothing here can reach a funded account: the gateway is pinned to
`TRADING_MODE=paper` and the harness refuses ports 7496, 4001 and 4003.

## Host

Oracle Cloud Always Free, shape `VM.Standard.A1.Flex` (Arm), 2 OCPU / 12 GB,
Ubuntu 24.04 aarch64. The gateway image is multi-architecture, so the same
compose file runs on an amd64 host (for example a GCP `e2-micro` with a 2 GB swap
file and `JAVA_HEAP_SIZE` lowered to 768).

Oracle reclaims Always Free instances that sit below 20% CPU, network and memory
utilisation for seven days. Upgrade the tenancy to Pay As You Go (still free within
Always Free limits) and add a budget alert at US$1 so any charge is visible at once.

## Setup

1. Create the instance with an SSH key. Leave the default security list, which
   admits only port 22; no other ingress is required.
2. On the VM:

   ```bash
   sudo timedatectl set-timezone America/New_York
   sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
   sudo usermod -aG docker "$USER"   # log out and back in afterwards
   sudo mkdir -p /opt/ivcrush && sudo chown "$USER" /opt/ivcrush
   ```

3. Locally, from the repository root: `bash deploy/pack.sh`, then
   `scp ivcrush_deploy.tar.gz <user>@<vm>:/tmp/`.
4. On the VM:

   ```bash
   cd /opt/ivcrush && tar -xzf /tmp/ivcrush_deploy.tar.gz
   cd deploy
   cp gateway.env.example gateway.env && cp runner.env.example runner.env
   chmod 600 gateway.env runner.env     # then fill both in
   mkdir -p state/live state/control
   docker compose up -d ib-gateway
   docker compose logs -f ib-gateway    # wait for the API to report it is listening
   docker compose --profile run build runner
   docker compose --profile run run --rm runner   # one dry-run pass
   crontab crontab
   ```

5. Read `state/control/logs/paper_daily_<date>.log`. A healthy dry run connects,
   lists candidates with non-NaN quotes and writes a heartbeat row.

## Operating

| Action | Command (in `/opt/ivcrush/deploy`) |
|---|---|
| Transmit paper orders | `touch state/control/TRANSMIT_OK` |
| Return to dry run | `rm state/control/TRANSMIT_OK` |
| Halt new entries (exits continue) | `touch state/live/STOP` |
| Run a pass now | `docker compose --profile run run --rm runner` |
| Gateway status | `docker compose ps` and `docker compose logs --tail 100 ib-gateway` |
| Check the gateway is logged in (restart once if not) | `./gateway_preflight.sh`; cron runs it at 15:00 ET, log in `state/control/gateway_preflight.log` |
| Inspect the gateway UI | `ssh -L 5900:127.0.0.1:5900 <user>@<vm>`, then VNC to `localhost:5900` |
| Copy the book home | `scp '<user>@<vm>:/opt/ivcrush/deploy/state/live/*.parquet' outputs/live/` |
| Deploy a code change | re-pack, copy, extract, `docker compose --profile run build runner` |

Positions and ledgers live in `state/live/`, logs and the report in
`state/control/`. A missed day, an unreachable gateway, or an entry pass where no
candidate prices posts a failure to `HEALTHCHECK_URL` with the log tail attached.
Closed sessions and 13:00 early closes skip by design and are logged as such;
positions due on an early close exit on the next session.

## Book definition

`runner.env` sets the rule, the universe and the timing. The default is the
unconditional book on the 346-name broad universe with session-aware (one-session)
holds, which is the population and holding period of the out-of-sample baseline.
Every open position records `selection_rule`, `implied_move`,
`iv_term_spread_nearest`, `entry_mid_ps` and `entry_rel_spread`, so a candidate
selector can be scored on the same forward trades without changing what is traded.

## Teardown

Terminate the instance with "permanently delete the attached boot volume"
selected, then delete its VCN and the budget alert. Copy `state/live/` home first.
