#!/usr/bin/env bash
set -euo pipefail

REPO="/home/hudlowe/src/mrrc-hdr-qa"
VENV="$REPO/.venv/bin/python"
LOGDIR="$REPO/logs"
mkdir -p "$LOGDIR"

# ---- MRQART daily QA config ----
export MRQART_PROJECT='Brain^wpc-%'
export MRQART_SEQNAME='RewardedAnti%'
export MRQART_PER_PAIR_LIMIT=3

# Only look at today's acquisitions
export MRQART_SINCE="$(date +%m-%d-%Y)"

# --- only send if issues ---
unset MRQART_FORCE_EMAIL

# Still regenerate the static dashboard each run
export MRQART_WEB_LOG="$REPO/static/mrqart_log.jsonl"
export MRQART_WEB_HTML="$REPO/static/mrqart_report.html"
export MRQART_WEB_TITLE="MRRC Header QA — Feed"

cd "$REPO"
"$VENV" -m mrqart.email_latest_flip >>"$LOGDIR/mrqart_daily.log" 2>&1

