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

TagTuple = tuple[int, int]


def tagpair_to_hex(csv_str) -> TagTuple:
    """
    move our text files has tags like "0051,1017"
    to pydicom indexe like (0x51,0x1017)

    :param csv_str: comma separated string to convert
    :return: dicom header tag hex pair

    >>> tagpair_to_hex("0051,1017")
    ('0x51', '0x1017')
    """
    return tuple(hex(int(x, 16)) for x in csv_str.split(","))


TagDicts = list[
    TypedDict("Tag", {"name": str, "tag": TagTuple, "loc": str, "desc": str})
]


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

    # second pass to make '0x0018,0x0080' into (0x0018,0x0080)
    for i in range(len(tags)):
        if re.search("^[0-9]{4},", tags[i]["tag"]):
            tags[i]["tag"] = tagpair_to_hex(tags[i]["tag"])
            tags[i]["loc"] = "header"
        else:
            tags[i]["loc"] = "csa"

    return tags


def csa_fetch(csa_tr: dict, itemname: str) -> str:
    """
    safely look into ``csa_tr`` dicom dictionary.
    Expect nested structure like ``'tags'->itemname->'items'->[0]``.

    In future, might want to check itemname and pull out more than the first array item.

    >>> csa_fetch({'notags':'badinput'}, 'PhaseEncodingDirectionPositive')
    'null'
    >>> csa_fetch({'tags':{'ImaPATModeText': {'items': [1]}}}, 'ImaPATModeText')
    1
    """
    try:
        val = csa_tr["tags"][itemname]["items"]
        val = val[0] if val else NULLVAL.value
    except KeyError:
        val = NULLVAL.value
    return val


def read_csa(csa) -> list[str]:
    """
    extract parameters from siemens CSA
    :param csa: content of siemens private tag (0x0029, 0x1010)
    :return: [pepd, ipat] is phase encode positive direction and GRAPA iPATModeText

    >>> read_csa(None) is None
    True
    """
    if csa is None:
        return None
    csa = csa.value
    try:
        csa_tr = csareader.read(csa)
    except csareader.CSAReadError:
        return None
    return csa_tr


def read_tags(dcm_path: os.PathLike, tags: TagDicts) -> dict[str, str]:
    """
    Read dicom header and isolate tags

    :param dcm_path: dicom file with headers to extract
    :param tags: ordered dictionary with 'tag' key as hex pair, see :py:func:`tagpair_to_hex`
    :return: dict[tag,value] values in same order as ``tags`` \

    >>> tr = {'name': 'TR', 'tag': (0x0018,0x0080), 'loc': 'header'}
    >>> ipat = {'name': 'iPAT', 'tag': 'ImaPATModeText', 'loc': 'csa'}
    >>> list(read_tags('example_dicoms/RewardedAnti_good.dcm', [ipat, tr]).values())
    ['p2', '1300', 'example_dicoms/RewardedAnti_good.dcm']

    >>> list(read_tags('example_dicoms/DNE.dcm', [ipat,tr]).values())
    ['null', 'null', 'example_dicoms/DNE.dcm']
    """
    if not os.path.isfile(dcm_path):
        raise Exception(f"Bad path to dicom: '{dcm_path}' DNE")
    try:
        dcm = pydicom.dcmread(dcm_path)
    except pydicom.errors.InvalidDicomError:
        logging.error("cannot read header in %s", dcm_path)
        nulldict = {tag["name"]: "null" for tag in tags}
        nulldict["dcm_path"] = dcm_path
        return nulldict

    out = dict()
    csa = read_csa(dcm.get((0x0029, 0x1010)))
    for tag in tags:
        k = tag["name"]
        if tag["loc"] == "csa":
            out[k] = csa_fetch(csa, tag["tag"]) if csa is not None else NULLVAL.value
        else:
            out[k] = dcm.get(tag["tag"], NULLVAL).value

    out["dcm_path"] = dcm_path
    return out


class DicomTagReader:
    """Class to cache :py:func:`read_known_tags` output"""

    def __init__(self):
        self.tags = read_known_tags()

    def read_dicom_tags(self, dcm_path: os.PathLike) -> dict:
        """return values of dicom header priority fields
        ordered as defined in ``taglist.txt``
        :param dcm_path: path to dciom
        :return: dict[taglist.txt tagname, tag value]

        >>> dtr = DicomTagReader()
        >>> hdr = dtr.read_dicom_tags('example_dicoms/RewardedAnti_good.dcm')
        >>> list(hdr.values()) # doctest: +ELLIPSIS
        [1, 'p2', '154833.265000', '20220913', ...

        >>> list(hdr.values())[-1]
        'example_dicoms/RewardedAnti_good.dcm'
        """
        return read_tags(dcm_path, self.tags)


if __name__ == "__main__":
    dtr = DicomTagReader()
    logging.info("processing %d dicom files", len(sys.argv) - 1)
    for dcm_path in sys.argv[1:]:
        all_tags = dtr.read_dicom_tags(dcm_path).values()
        print("\t".join(all_tags))
