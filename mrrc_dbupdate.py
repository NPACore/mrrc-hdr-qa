#!/usr/bin/env python3
"""
Find MRRC organized study acquisitions directories newer than what's in the DB
and update them.
"""
import logging
import os
import re
import subprocess
from datetime import timedelta
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


PathLike = str


def find_first_dicoms(session_root: PathLike) -> list[PathLike]:
    """
    Find a representative dicom for each acquisition in ``session_root``.

    :param session_root: path to session root directory. likely like ``.../ProjectName/yyyy.mm.dd-hh.mm.ss``
    :return: list of first dicoms like ``sessroot/subjid/acquisitonname/MR*``
    """
    first_dicoms = []
    if not os.path.isdir(session_root):
        raise Exception(f"{session_root} is not a directory!")
    for seqdir in glob(os.path.join(session_root, "*/*/")):
        if not os.path.isdir(seqdir) or re.search("PhysioLog|PhoenixZIPReport", seqdir):
            continue
        findcmd = f"find '{seqdir}' -maxdepth 1 -type f \( -iname '*.dcm' -or -iname 'MR.*' -or -iname '*.IMA' \) -print -quit"
        dcm = subprocess.check_output(findcmd, shell=True).decode("utf-8").strip()
        if dcm:
            logging.debug("found first dcm '%s'", dcm)
            first_dicoms.append(dcm)
        else:
            logging.warning("no dicoms found in %s", seqdir)
    return first_dicoms


def update_mrrc_db(project_dir_list: list[PathLike] = None):
    """
    Use DB dates to find projects with new sessions. Add acquisitions.
    Dicoms in structure like ``Project/yyyy.mm.dd-*/SessionId/AcqustionName-FOV.num/MR*``

    :param project_dir_list: list of project dirs. Default is ``glob("/disk/mace2/scan_data/*")``.
    """
    if not project_dir_list:
        project_dir_list = glob("/disk/mace2/scan_data/*")

    db = acq2sqlite.DBQuery()
    dtr = dcmmeta2tsv.DicomTagReader()
    VERYRECENT = db.most_recent()
    for pdir in project_dir_list:
        if not is_project(pdir):
            next
        project = os.path.basename(pdir)
        recent = db.most_recent("%" + project)

        #: if no data from any other pass, use the most recent DB pass as time to check
        #: this will be a problem if this script isn't used to update and a existing folder is updated in between runs
        if not recent or recent == "None":
            recent = VERYRECENT

        #: sequence time is older than folder copy to gyrus time
        #: reset time to midnight and go one day ahead
        nextday = recent.date() + timedelta(days=1)
        newer = f"-newermt '{nextday}'"

        # use external find command to list all the directories newer than our cutoff
        cmd = f"find '{pdir}' -maxdepth 1 -mindepth 1 {newer} -type d -print0"
        res = subprocess.check_output(cmd, shell=True)
        newsessions = res.decode("utf-8").split("\0")[0:-1]
        logging.info(
            f"project:'{project}'; res='{recent}'; search for {newer}: {len(newsessions)}"
        )

        for ses in newsessions:
            acq_dicoms = find_first_dicoms(ses)
            logging.info("ses '%s' has %d dicoms found", ses, len(acq_dicoms))
            for acq in acq_dicoms:
                logging.debug("processing first dcm from newer acq '%s'", acq)
                if not acq or not os.path.isfile(acq):
                    logging.warning("%s bad acq file '%s'", ses, acq)
                    continue
                all_tags = dtr.read_dicom_tags(acq)
                if os.environ.get("DRYRUN"):
                    logging.info(all_tags)
                else:
                    db.dict_to_db_row(all_tags)

        db.sql.commit()


if __name__ == "__main__":
    update_mrrc_db()
