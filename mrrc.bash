#!/usr/bin/env bash
# initial big db run on cerebro2 
# 20241026 -init

# paper over centOS7+guix config issues
export SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt LC_ALL=C
make .venv
. .venv/bin/activate

echo "[$(date +%s)] parse dicoms start" | tee build.log
./00_build_db.bash /disk/mace2/scan_data/*

echo "[$(date +%s)] add to db start" | tee -a build.log
cat db/*.txt | ./acq2sqlite.py

echo "[$(date +%s)] finished" | tee -a build.log
