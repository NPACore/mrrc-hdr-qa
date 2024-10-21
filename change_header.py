#!/usr/bin/env python3
"""
Modify protocol names.
"""
import os
from pathlib import Path
from typing import List, Optional
from itertools import chain
import pydicom


def change_protocol_name(
    dcm_dir: Path, new_data: List[pydicom.DataElement], out_dir: Optional[Path] = None
):
    """
    Change specified tags of all dicoms in a directory. Optionally make copies in out_dir.

    :param dcm_dir:  input directory with dicom files (``MR*``, ``*IMA`` , or ``*dcm``)
    :param new_data: list of data elements to replace
        like ``[pydicom.DataElement(value="newpname", VR="LO", tag=(0x0018, 0x1030))]``
    :param out_dir:  Optional. Where to save modified dicoms
    :return: example modified dicom. last if out_dir, first and only if no ``out_dir``.

    sideffect:  writes copies of dcm_dir dicoms inot out_dir unless out_dir is None.

    >>> new_data = [pydicom.DataElement(value="newpname", VR="LO", tag=(0x0018, 0x1030))]
    >>> ex_path = Path('example/dicom/11903_20221222/HabitTask_704x752.18/')
    >>> ex = change_protocol_name(ex_path, new_data)
    >>> ex.ProtocolName
    'newpname'
    """
    all_dicoms = chain(dcm_dir.glob("MR*"), dcm_dir.glob("*IMA"), dcm_dir.glob("*dcm"))
    ex_dcm = None
    for ex_dcm_file in all_dicoms:
        ex_dcm = pydicom.dcmread(ex_dcm_file)

        for datum in new_data:
            ex_dcm[datum.tag] = datum

        # dont need to do anything if not writing files
        if out_dir is None:
            return ex_dcm

        new_file = os.path.join(out_dir, os.path.basename(ex_dcm_file))
        # assume if we have one, we have them all (leave loop at first existing)
        if os.path.exists(new_file):
            return ex_dcm

        # and save out
        os.makedirs(out_dir, exist_ok=True)
        ex_dcm.save_as(new_file)

    return ex_dcm


if __name__ == "__main__":
    new_tags = [
        # Repetition Time
        pydicom.DataElement(value="1301", VR="DS", tag=(0x0018, 0x0080)),
        # Patient ID
        pydicom.DataElement(value="mod1", VR="PN", tag=(0x0010, 0x0010)),
        pydicom.DataElement(value="mod1", VR="LO", tag=(0x0010, 0x0020)),
        ## anonymize
        # DOB
        pydicom.DataElement(value="19991231", VR="DA", tag=(0x0010, 0x0030)),
        # age
        pydicom.DataElement(value="100Y", VR="AS", tag=(0x0010, 0x1010)),
        # sex
        pydicom.DataElement(value="20240131", VR="CS", tag=(0x0010, 0x0040)),
    ]

    change_protocol_name(
        Path("example/dicom/11903_20221222/HabitTask_704x752.18/"),
        new_tags,
        Path("example/dicom/mod1/HabitTask/"),
    )
