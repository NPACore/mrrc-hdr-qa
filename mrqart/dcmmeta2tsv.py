#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydicom",
# ]
# ///
"""
Give a tab separated metadata value line per dicom file.
"""
import logging
import os
import re
import sys
import warnings
from typing import Optional, TypedDict
from importlib import resources
import pydicom

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    # UserWarning: The DICOM readers are highly experimental...
    from nibabel.nicom import csareader

logging.basicConfig(level=os.environ.get("LOGLEVEL", logging.INFO))


class NULLVAL:
    """Container to imitate ``pydicom.dcmread``.
    object that has ``obj.value`` for when a dicom tag does not exist.
    Using "null" to match AFNI's dicom_hinfo missing text"""

    value: str = "null"


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


#: TagKey is dicom header e.g. TR in taglist.txt
TagKey = str

TagDicts = list[
    TypedDict("Tag", {"name": TagKey, "tag": TagTuple, "loc": str, "desc": str})
]

#: keys are names from ``taglist.txt``, also has ``dcm_path`` key for file
TagValues = dict[TagKey, str]


def read_known_tags(tagfile: Optional[str] = None) -> TagDicts:
    """
    Read the tag list from package data (mrqart/data/taglist.txt) so it works
    from source, editable installs, and wheels. You can override with a path
    by passing tagfile=<path>.
    """
    if tagfile is None or os.path.basename(tagfile) == "taglist.txt":
        # read packaged data
        txt = resources.files("mrqart.data").joinpath("taglist.txt").read_text(encoding="utf-8")
        lines = txt.splitlines()
    else:
        # allow explicit external files for power users
        with open(tagfile, "r") as f:
            lines = f.read().splitlines()

    tags = [
        dict(zip(["name", "tag", "desc"], line.split("\t")))
        for line in lines
        if not re.search(r"^name|^#", line)
    ]

    # second pass to make '0x0018,0x0080' into (0x0018,0x0080) and set 'loc'
    for i in range(len(tags)):
        name = tags[i]["name"]
        if re.search(r"^[0-9]{4},", tags[i]["tag"]):
            tags[i]["tag"] = tagpair_to_hex(tags[i]["tag"])
            tags[i]["loc"] = "header"
        elif name.lower() == "shims":   # case-insensitive to match 'Shims'
            tags[i]["loc"] = "asccov"
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


def read_shims(csa_s: Optional[dict]) -> list:
    """
    :param: csa_s ``0x0029,0x1020`` CSA **Series** Header Info::
        csa_s = dcmmeta2tsv.read_csa(dcm.get(())

    :return: list of shim values in order of CHM matlab code

    CHM maltab code concats
      sAdjData.uiAdjShimMode
      sGRADSPEC.asGPAData[0].lOffset{X,Y,Z}
      sGRADSPEC.alShimCurrent[0:4]
      sTXSPEC.asNucleusInfo[0].lFrequency

    >>> csa_s = pydicom.dcmread('example_dicoms/RewardedAnti_good.dcm').get((0x0029, 0x1020))
    >>> ",".join(read_shims(read_csa(csa_s)))
    '1174,-2475,4575,531,-20,59,54,-8,123160323,4'
    >>> read_shims(None)  # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
    ['null', ...'null']
    """

    if csa_s is None:
        csa_s = {}
    try:
        asccov = csa_s["tags"]["MrPhoenixProtocol"]["items"][0]
    except KeyError:
        return [NULLVAL.value] * 10

    key = "|".join(
        [
            "sAdjData.uiAdjShimMode",
            "sGRADSPEC.asGPAData\\[0\\].lOffset[XYZ]",
            "sGRADSPEC.alShimCurrent\\[[0-4]\\]",
            "sTXSPEC.asNucleusInfo\\[0\\].lFrequency",
        ]
    )

    # keys are like
    #   sGRADSPEC.asGPAData[0].lOffsetX\t = \t1174
    reg = re.compile(f"({key})\\s*=\\s*([^\\s]+)")
    res = reg.findall(asccov)
    # could be more rigerous about order by moving tuple results into dict
    return [x[1] for x in res]


def read_csa(csa) -> Optional[dict]:
    """
    extract parameters from siemens CSA
    :param csa: content of siemens private tag (0x0029, 0x1010)
    :return: nibabel's csareader dictionary or None if cannot read

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


def read_tags(dcm_path: os.PathLike, tags: TagDicts) -> TagValues:
    """
    Read dicom header and isolate tags

    :param dcm_path: dicom file with headers to extract
    :param tags: ordered dictionary with 'tag' key as hex pair, see :py:func:`tagpair_to_hex`
    :return: dict[tag,value] values in same order as ``tags``

    >>> tr = {'name': 'TR', 'tag': (0x0018,0x0080), 'loc': 'header'}
    >>> ipat = {'name': 'iPAT', 'tag': 'ImaPATModeText', 'loc': 'csa'}
    >>> list(read_tags('example_dicoms/RewardedAnti_good.dcm', [ipat, tr]).values())
    ['p2', '1300.0', 'example_dicoms/RewardedAnti_good.dcm']

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
        if k == "Shims":
            # 20241118: add shims
            csa_s = read_csa(dcm.get((0x0029, 0x1020)))
            shims = read_shims(csa_s)
            out[k] = ",".join(shims)
        elif tag["loc"] == "csa":
            out[k] = csa_fetch(csa, tag["tag"]) if csa is not None else NULLVAL.value
        else:
            out[k] = dcm.get(tag["tag"], NULLVAL).value

        # 20241120: watch out for comments with newlines or tabs
        # can maybe just change 'Comments' instead of everything
        if type(out[k]) is str:
            out[k] = out[k].replace("\t", " ").replace("\n", " ")

    out["dcm_path"] = dcm_path
    return out


class DicomTagReader:
    """Class to cache :py:func:`read_known_tags` output"""

    def __init__(self):
        self.tags = read_known_tags()

    def read_dicom_tags(self, dcm_path: os.PathLike) -> TagValues:
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
        print("\t".join([str(x) for x in all_tags]))
