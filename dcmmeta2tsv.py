#!/usr/bin/env python3
"""
Give a tab separated metadata value line per dicom file.
"""
import logging
import os
import re
import sys
import warnings
from typing import TypedDict

import pydicom

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    # UserWarning: The DICOM readers are highly experimental...
    import nibabel.nicom.csareader as csareader

logging.basicConfig(level=os.environ.get("LOGLEVEL", logging.INFO))

#: object that has obj.value for when a dicom tag does not exist
#: using 'null' to match AFNI's dicom_hinfo
NULLVAL = type("", (object,), {"value": "null"})()


def tagpair_to_hex(csv_str) -> tuple[int, int]:
    """
    move our text files has tags like "0051,1017"
    to pydicom indexe like (0x51,0x1017)

    :param csv_str: comma separated string to convert
    :return: dicom header tag hex pair

    >>> tagpair_to_hex("0051,1017")
    ('0x51', '0x1017')
    """
    return tuple(hex(int(x, 16)) for x in csv_str.split(","))


TagDicts = list[TypedDict("Tag", {"name": str, "tag": str, "desc": str})]


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
    """

    >>> csa_fetch({'notags':'badinput'}, 'PhaseEncodingDirectionPositive')
    'null'
    """
    try:
        val = csa_tr["tags"][item]["items"]
        val = val[0] if val else NULLVAL.value
    except KeyError:
        val = NULLVAL.value
    return val


def read_csa(csa) -> list[str]:
    """
    extract parameters from siemens CSA
    :param csa: content of siemens private tag (0x0029, 0x1010)
    :return: [pepd, ipat] is phase encode positive direction and GRAPA iPATModeText

    >>> read_csa(None)
    ['null', 'null']
    """
    null = [NULLVAL.value] * 2
    if csa is None:
        return null
    csa = csa.value
    try:
        csa_tr = csareader.read(csa)
    except csareader.CSAReadError:
        return null
    pedp = csa_fetch(csa_tr, "PhaseEncodingDirectionPositive")
    ipat = csa_fetch(csa_tr, "ImaPATModeText")
    # order here matches 00_build_db.bash
    return [pedp, ipat]


def read_tags(dcm_path: os.PathLike, tags: TagDicts) -> list[str]:
    """
    :param dcm_path: dicom file with headers to extract
    :param tags: ordered dictionary with 'tag' key as hex pair, see :py:func:`tagpair_to_hex`
    :return: list of tag values in same order as ``tags`` \
    BUT with CSA headers ``pedp``, ``ipat`` prepended

    >>> tr = {'name': 'TR', 'tag': (0x0018,0x0080)}
    >>> read_tags('example_dicoms/RewardedAnti_good.dcm', [tr])
    ['1', 'p2', '1300', 'example_dicoms/RewardedAnti_good.dcm']

    >>> read_tags('example_dicoms/DNE.dcm', [tr])
    ['null', 'null', 'null', 'example_dicoms/DNE.dcm']
    """
    if not os.path.isfile(dcm_path):
        raise Exception("Bad path to dicom: '{dcm_path}' DNE")
    try:
        dcm = pydicom.dcmread(dcm_path)
    except pydicom.errors.InvalidDicomError:
        logging.error("cannot read header in %s", dcm_path)
        return ["null"] * (len(tags) + 2) + [dcm_path]

    meta = [dcm.get(tag_d["tag"], NULLVAL).value for tag_d in tags]

    csa_tags = read_csa(dcm.get((0x0029, 0x1010)))

    # NB. arrays are '[x, y, z]' instead of ' x y z ' or 'x/y'
    # like in dicom_hdr (00_build_db.bash)
    all_tags = [str(x) for x in csa_tags + meta] + [dcm_path]
    return all_tags


if __name__ == "__main__":
    tags = read_known_tags()
    for i in range(len(tags)):
        tags[i]["tag"] = tagpair_to_hex(tags[i]["tag"])

    logging.info("processing %d dicom files", len(sys.argv) - 1)
    for dcm_path in sys.argv[1:]:
        all_tags = read_tags(dcm_path, tags)
        print("\t".join(all_tags))
