#!/usr/bin/env bash
cd $(dirname "$0")
. .venv/bin/activate
./mrqart.py --watch-dirs /data/dicomstream/ -p 8080
