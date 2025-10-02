#!/usr/bin/env bash
# initial big db run on cerebro2 
# 20241026 -init

# paper over centOS7+guix config issues
export SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt LC_ALL=C LOGLEVEL=WARN
# system dependencies:
#   guix install parallel python sqlite3
# use in cron:
#   0 0 * * * /path/to/00_build_mrrc_db.bash

cd "$(dirname "$0")"
make db.sqlite
make .venv/bin/pydicom  # ensure we depends for build_db.bash:dcmmeta2tsv.py and acq2sqlite.py
. .venv/bin/activate

log(){ echo "$(date +"[%s] %F %T"):: $*" | tee -a build.log; }

log parse dicoms start
./build_db.bash /disk/mace2/scan_data/WPC-*

log starting sqlite db
#cat db/*.txt | ./acq2sqlite.py
for db in db/*.txt; do
  echo $db
  cat $db | ./acq2sqlite.py
done

log build template
make templates.tsv
