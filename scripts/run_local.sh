#!/bin/bash
# Run by launchd every few minutes. Put GMAIL_APP_PASSWORD=... in ~/.sproochentest.env for email (push works without it).
cd "$(dirname "$0")/.."
[ -f "$HOME/.sproochentest.env" ] && set -a && . "$HOME/.sproochentest.env" && set +a
export STATE_FILE="$PWD/state/local_status.json"
echo "=== $(date)"
exec .venv/bin/python scripts/check_availability.py
