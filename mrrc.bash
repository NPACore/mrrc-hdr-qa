#!/usr/bin/env bash
# initial big db run on cerebro2 
# 20241026 -init

# paper over centOS7+guix config issues
export SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt LC_ALL=C LOGLEVEL=WARN
make .venv
. .venv/bin/activate

log(){ echo "$(date +"[%s] %F %T"):: $*" | tee -a build.log; }

log parse dicoms start
./00_build_db.bash /disk/mace2/scan_data/WPC-*

log starting sqlite db
cat db/*.txt | ./acq2sqlite.py

log finished
