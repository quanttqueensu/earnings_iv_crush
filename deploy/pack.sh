#!/usr/bin/env bash
# pack.sh -- bundle exactly what the VM needs into ivcrush_deploy.tar.gz.
#
# Packs from the working tree, not from git, so the bundle matches what was
# tested locally. Credential files (*.env) and VM state are never included.
#
# Usage (from the repository root, Git Bash or any POSIX shell):
#     bash deploy/pack.sh
#     scp ivcrush_deploy.tar.gz <user>@<vm>:/tmp/

set -euo pipefail
cd "$(dirname "$0")/.."

files=(
    requirements.txt pyproject.toml README.md data/universe_broad.csv
    earnings_iv_crush
    scripts/paper_trade_ibkr.py scripts/forward_report.py scripts/sweep_term_panel.py
    outputs/research/events_megacap_v2.parquet
    outputs/research/events_broad_oos_2025.parquet
    deploy/docker-compose.yml deploy/Dockerfile.runner deploy/Dockerfile.runner.dockerignore
    deploy/run_paper_daily.sh deploy/session_check.py deploy/crontab
    deploy/gateway_probe.py deploy/gateway_preflight.sh
    deploy/gateway.env.example deploy/runner.env.example deploy/README.md
)
for f in "${files[@]}"; do
    [ -e "$f" ] || { echo "missing: $f" >&2; exit 1; }
done

tar --exclude='__pycache__' --exclude='*.pyc' -czf ivcrush_deploy.tar.gz "${files[@]}"
echo "wrote ivcrush_deploy.tar.gz ($(du -h ivcrush_deploy.tar.gz | cut -f1))"
tar -tzf ivcrush_deploy.tar.gz | grep -E '\.env$' && { echo "credential file in bundle" >&2; exit 1; }
exit 0
