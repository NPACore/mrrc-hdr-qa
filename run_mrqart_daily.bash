#!/usr/bin/env bash
set -euo pipefail

# TODO: use path relative to script path: "$0"
# REPO=$(cd $(diranme $(readlink -f "$0")); pwd -L)
REPO="/home/hudlowe/src/mrrc-hdr-qa"

# TODO: use test for uv, use that instead of venv
# uv run tool mrqart -- python3 -m myrqart.email_latest_flip
# if in REPO dir, can just use 'python3' instead of $VENV's python?
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

# TODO: use argparser instead of global env?
# Still regenerate the static dashboard each run
export MRQART_WEB_LOG="$REPO/static/mrqart_log.jsonl"
export MRQART_WEB_HTML="$REPO/static/mrqart_report.html"
export MRQART_WEB_TITLE="MRRC Header QA — Feed"

cd "$REPO"
"$VENV" -m mrqart.email_latest_flip >>"$LOGDIR/mrqart_daily.log" 2>&1

