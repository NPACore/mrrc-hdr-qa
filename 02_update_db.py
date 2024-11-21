#!/usr/bin/env python3
"""
Add newer scans to DB
"""
import os
import re
from glob import glob

import acq2sqlite
import dcmmeta2tsv


def is_project(pdir: str) -> bool:
    """
    Is input a MR project dir?
    should have subfolder like ``2024.06.27-09.19.11/``

    :param pdir: directory to test
    :return: True if is a project directory

    #>>> is_project('/disk/mace2/scan_data/WPC-8620/')
    #True
    #>>> is_project('/disk/mace2/scan_data/7T/')
    #False
    """
    if not os.path.isdir(pdir):
        return False
    for sesdir in os.listdir(pdir):
        if re.search("^2[0-9.-]{18}$", sesdir):
            return True
    return False


db = acq2sqlite.DBQuery()
for pdir in glob("/disk/mace2/scan_data/W*"):
    if not is_project(pdir):
        next
    project = os.path.basename(pdir)
    recent = db.most_recent("%" + project)
    print(f"project:'{project}'; res='{recent}'")
