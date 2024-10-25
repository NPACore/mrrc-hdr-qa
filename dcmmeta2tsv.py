#!/usr/bin/env python3
"""
Give a tab separated metadata value line per dicom file.
"""
import os
import sys
import re
import pydicom

# import warnings
# warnings.filterwarnings("ignore", module="nibabel.nicom.csareader")
import nibabel.nicom.csareader as csareader


def tagpair_to_hex(csv_str):
    """
    move our text files has tags like "0051,1017"
    to pydicom indexe like (0x51,0x1017)
    """
    return tuple(hex(int(x, 16)) for x in csv_str.split(","))


def read_known_tags(tagfile="taglist.txt"):
    """
    read in tsv file like with header name,tag,desc.
    skip comments and header
    """
    with open(tagfile, "r") as f:
        tags = [
            dict(zip(["name", "tag", "desc"], line.split("\t")))
            for line in f.readlines()
            if not re.search("^name|^#", line)
        ]
    return tags


if __name__ == "__main__":
    tags = read_known_tags()
    for i in range(len(tags)):
        tags[i]["tag"] = tagpair_to_hex(tags[i]["tag"])

    for dcm_path in sys.argv[1:]:
        if not os.path.isfile(dcm_path):
            raise Exception("Bad command line argument: '{dcm_path}' DNE")
        dcm = pydicom.dcmread(dcm_path)
        meta = [dcm[tag_d["tag"]].value for tag_d in tags]

        csa_str = dcm[(0x0029, 0x1010)].value
        csa_tr = csareader.read(csa_str)
        pedp = csa_tr["tags"]["PhaseEncodingDirectionPositive"]["items"]
        pedp = pedp[0] if pedp else "null"
        ipat = csa_tr["tags"]["ImaPATModeText"]["items"]
        ipat = ipat[0] if ipat else "null"
        # order here matches 00_build_db.bash
        csa_tags = [pedp, ipat]
        # NB. arrays are '[x, y, z]' instead of ' x y z ' or 'x/y'
        # like in dicom_hdr (00_build_db.bash)
        all_tags = [str(x) for x in csa_tags + meta] + [dcm_path]
        print("\t".join(all_tags))
