#!/usr/bin/env python3
"""
Give a tab separated metadata value line per dicom file.
"""
import os
import sys
import re
import pydicom
import logging
from typing import TypedDict

# import warnings
# warnings.filterwarnings("ignore", module="nibabel.nicom.csareader")
import nibabel.nicom.csareader as csareader

logging.basicConfig(level=logging.INFO)
# object that has obj.value for when a dicom tag does not exist
NULLVAL = type('',(object,),{"value": "null"})()

def tagpair_to_hex(csv_str) -> tuple[int,int]:
    """
    move our text files has tags like "0051,1017"
    to pydicom indexe like (0x51,0x1017)

    :param csv_str: comma separated string to convert
    :return: dicom header tag hex pair

    >>> tagpair_to_hex("0051,1017")
    ('0x51','0x1017')
    """
    return tuple(hex(int(x, 16)) for x in csv_str.split(","))

TagDicts = list[TypedDict('Tag', {'name': str, 'tag': str, 'desc': str})]
def read_known_tags(tagfile="taglist.txt") -> TagDicts:
    """
    read in tsv file like with header name,tag,desc.
    skip comments and header

    :param tagfile: text tsv file to get name,tag(hex pair),desc from
    :return: file parsed into a list of dictonaires
    """
    with open(tagfile, "r") as f:
        tags = [
            dict(zip(["name", "tag", "desc"], line.split("\t")))
            for line in f.readlines()
            if not re.search("^name|^#", line)
        ]
    return tags

def csa_fetch(csa_tr: dict, item: str) -> str:
    try:
        val = csa_tr["tags"]["PhaseEncodingDirectionPositive"]["items"]
        val = val[0] if val else "null"
    except KeyError:
        val = 'null'
    return val

def read_tags(dcm_path: os.PathLike, tags: TagDicts) -> list[str]:
    """
    :param dcm_path: dicom file with headers to extract
    :param tags: ordered dictionary with 'tag' key as hex pair, see :py:func:`tagpair_to_hex`
    :return: list of tag values in same order as ``tags``
    BUT with CSA headers ``pedp``, ``ipat`` prepended
    """
    if not os.path.isfile(dcm_path):
        raise Exception("Bad path to dicom: '{dcm_path}' DNE")
    dcm = pydicom.dcmread(dcm_path)
    meta = [dcm.get(tag_d["tag"],NULLVAL).value for tag_d in tags]

    csa = dcm.get((0x0029, 0x1010))
    if csa:
        csa_str = csa.value
        csa_tr = csareader.read(csa_str)
        pedp = csa_fetch(csa_tr, "PhaseEncodingDirectionPositive")
        ipat = csa_fetch(csa_tr, "ImaPATModeText")
        # order here matches 00_build_db.bash
        csa_tags = [pedp, ipat]
    else:
        csa_tags = ['null','null']

    # NB. arrays are '[x, y, z]' instead of ' x y z ' or 'x/y'
    # like in dicom_hdr (00_build_db.bash)
    all_tags = [str(x) for x in csa_tags + meta] + [dcm_path]
    return all_tags


if __name__ == "__main__":
    tags = read_known_tags()
    for i in range(len(tags)):
        tags[i]["tag"] = tagpair_to_hex(tags[i]["tag"])

    logging.info("processing %d dicom files", len(sys.argv)-1)
    for dcm_path in sys.argv[1:]:
        all_tags = read_tags(dcm_path, tags)
        print("\t".join(all_tags))
