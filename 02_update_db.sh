#!/usr/bin/env bash
#
# update database querying just for new files
# run in cron like
#   0 0 * * * /path/to/02_update_db.sh

cd "$(dirname "$0")"
mkdir -p log
! test -r ./db.sqlite && echo "no DB file '$_'!" && exit 1
. .venv/bin/activate
./mrrc_dbupdate.py  >> log/update-db.log 2>&1 
