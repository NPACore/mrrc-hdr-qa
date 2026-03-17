#!/usr/bin/env bash
set -euo pipefail

REPO="/home/hudlowe/src/mrrc-hdr-qa"
VENV="$REPO/.venv/bin/python"
LOGDIR="$REPO/logs"
mkdir -p "$LOGDIR"

# ---- MRQART daily QA config ----
# All projects / all sequences
export MRQART_PROJECT='%'
export MRQART_SEQNAME='%'

# Limit per (Project,Sequence)
export MRQART_PER_PAIR_LIMIT=0

# Only look at yesterday's acquisitions
export MRQART_SINCE="$(date -d 'yesterday' +%m-%d-%Y)"

# Send an email even if no issues are found
export MRQART_FORCE_EMAIL=1

# export MRQART_SKIP_CASEONLY=1

# Web dashboard (static) — still regenerate each run
export MRQART_WEB_LOG="$REPO/static/mrqart_log.jsonl"
export MRQART_WEB_HTML="$REPO/static/mrqart_report.html"
export MRQART_WEB_TITLE="MRRC Header QA — Feed"

cd "$REPO"
"$VENV" -m mrqart >>"$LOGDIR/mrqart_daily.log" 2>&1
