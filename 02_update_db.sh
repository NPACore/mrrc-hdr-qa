#!/usr/bin/env bash
cd "$(dirname "$0")"
mkdir -p log
! test -r ./db.sqlite && echo "no DB file '$_'!" && exit 1
. .venv/bin/activate
./mrrc_dbupdate.py  >> log/update-db.log 2>&1 
