#!/usr/bin/env python3
"""
quick cli tool to run template checker against tsv input
likely form ``./dcmmeta2tsv.py $file``::
    ./dcmmeta2tsv.py $file | ./check_template.py

Added 2024-10-08. Consider removing 2024-11-20
"""
import sys

from acq2sqlite import DBQuery, have_pipe_data

db = DBQuery()

if not have_pipe_data():
    print("script expects piped data")
    sys.exit(1)

with sys.stdin as f:
    while line := f.readline():
        d = db.tsv_to_dict(line)
        # PixelResol -- different resolutions depending on where it came from?
        # pydicom show /data/dicomstream/20241016.MRQART_test.24.10.16_16_50_16_DST_1.3.12.2.1107.5.2.43.67078/001_000012_000001.dcm::PixelSpacing
        # [2.31111, 2.31111]
        # pydicom show wpc-8986/2024.10.16-13.47.56/1000/SpinEchoFieldMap_1_672x720.19/MR.1.3.12.2.1107.5.2.43.67078.2024101614262767573523268|grep -P 'Pixel Spacing|Acquisition (Date|Time)'
        # (0008, 0022) Acquisition Date                    DA: '20241016'
        # (0008, 0032) Acquisition Time                    TM: '142624.795000'
        # (0028, 0030) Pixel Spacing                       DS: [2.3111112117767, 2.3111112117767]
        param_id = db.search_acq_param(d)
        print(param_id)
        matches = param_id and db.is_template(param_id)
        print(
            f"{d.get('Project')} {d.get('SequenceName')} @ {d.get('AcqDate')} matches template? {matches}"
        )
