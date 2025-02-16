#!/usr/bin/env python3
"""
Modify DICOM header information to simulate failing QA.
"""
import logging
import os
import random
import re
from datetime import datetime, timedelta
from itertools import chain
from pathlib import Path
from typing import List, Optional
import re

import pydicom

logging.basicConfig(level=os.environ.get("LOGLEVEL", logging.INFO))


def change_tags(
    dcm_dir: Path, new_data: List[pydicom.DataElement], out_dir: Optional[Path] = None
) -> Optional[pydicom.dataset.FileDataset]:
    """
    Change specified tags of all dicoms in a directory. Optionally make copies in out_dir.

    sideffect:  writes copies of ``dcm_dir`` dicoms into ``out_dir`` unless ``out_dir`` is ``None``.

    :param dcm_dir:  input directory with dicom files (``MR*``, ``*IMA`` , or ``*dcm``)
    :param new_data: list of data elements to replace
        like ``[pydicom.DataElement(value="newpname", VR="LO", tag=(0x0018, 0x1030))]``
    :param out_dir:  Optional. Where to save modified dicoms
    :return: example modified dicom. last if out_dir, first and only if no ``out_dir``.

    >>> new_data = [pydicom.DataElement(value="newpname", VR="LO", tag=(0x0018, 0x1030))]
    >>> ex_path = Path('example_dicoms/')
    >>> ex = change_tags(ex_path, new_data)
    >>> ex.ProtocolName
    'newpname'
    """
    # if given a single file, just rewrite that
    if os.path.isfile(dcm_dir):
        all_dicoms = [dcm_dir]
    else:
        # list comprehension so we can use len()
        all_dicoms = [
            x
            for x in chain(
                dcm_dir.glob("MR*"), dcm_dir.glob("*IMA"), dcm_dir.glob("*dcm")
            )
        ]

    ex_dcm = None
    for ex_dcm_file in all_dicoms:
        print(ex_dcm_file)

        try:
            ex_dcm = pydicom.dcmread(ex_dcm_file)
        except pydicom.errors.InvalidDicomError:
            logging.error("cannot read file as dicom %s", ex_dcm_file)
            continue

        for datum in new_data:
            ex_dcm[datum.tag] = datum

        # dont need to do anything if not writing files
        if out_dir is None:
            return ex_dcm

        if re.search(r"\.dcm$", os.path.basename(out_dir)) and len(all_dicoms) == 1:
            print(
                "# warning: output matches '.dcm' and only one input. assuming you're saving to a file"
            )

            new_file = out_dir
        else:
            new_file = os.path.join(out_dir, os.path.basename(ex_dcm_file))
        # assume if we have one, we have them all (leave loop at first existing)
        if os.path.exists(new_file):
            print(f"# {new_file} already exists")
            return ex_dcm

        # and save out
        print(f"save to {new_file}")
        os.makedirs(os.path.dirname(new_file), exist_ok=True)
        ex_dcm.save_as(new_file)

    return ex_dcm


def gen_anon() -> List[pydicom.DataElement]:
    """
    Make random date of birth, age, and sex.

    :return: list of DataElements with randomized values

    .. tip::

        Field tag type and location can be extracted like:

        .. code-block:: python

            x = pydicom.dcmread(example_fname)
            fields = ['AcquisitionDate', 'AcquisitionTime',
                      'PatientBirthDate', 'PatientAge', 'PatientSex']
            [x[k] for k in fields]

            # yields
            [(0008,0022) Acquisition Date                    DA: '20221222',
             (0008,0032) Acquisition Time                    TM: '092132.722500',
             (0010,0030) Patient's Birth Date                DA: '20070404',
             (0010,1010) Patient's Age                       AS: '015Y',
             (0010,0040) Patient's Sex                       CS: 'F']

    Where the tag is the tuple and "``XX``:" is the type

    """
    dob = f"{random.randrange(1980,2024):04d}0101"
    age = f"{random.randrange(8,100):03d}Y"
    sex = random.choice(["M", "F"])
    return [
        pydicom.DataElement(value=dob, VR="DA", tag=(0x0010, 0x0030)),
        pydicom.DataElement(value=age, VR="AS", tag=(0x0010, 0x1010)),
        pydicom.DataElement(value=sex, VR="CS", tag=(0x0010, 0x0040)),
    ]


def gen_ids(new_id: str) -> List[pydicom.DataElement]:
    """
    Generate ID DataElements.

    :param new_id: id string to put into pat name and pat id dicom headers.

    :return: ID DataElements List


    See :py:func:`gen_anon` for tag and VR info.

    >>> data_els = gen_ids('example_name')
    >>> data_els[0].value
    'example_name'
    >>> data_els[0].VR
    'PN'
    >>> data_els[0].tag # doctest: +NORMALIZE_WHITESPACE
    (0010, 0010)
    """
    return [
        pydicom.DataElement(value=new_id, VR="PN", tag=(0x0010, 0x0010)),
        pydicom.DataElement(value=new_id, VR="LO", tag=(0x0010, 0x0020)),
    ]


def gen_acqdates() -> List[pydicom.DataElement]:
    """
    Generate DataElements for random acquisition day and time.

    :return: ID DataElements List


    See :py:func:`gen_anon` for tag and VR info.
    """
    earliest = datetime(2020, 1, 1)
    rand_offset = random.randrange((datetime.now() - earliest).days * 24 * 60 * 60)
    rand_date = earliest + timedelta(seconds=rand_offset)
    ymd = rand_date.strftime("%Y%m%d")
    hms = rand_date.strftime("%H%M%S.000000")

    return [
        pydicom.DataElement(value=ymd, VR="DA", tag=(0x0008, 0x0022)),
        pydicom.DataElement(value=hms, VR="TM", tag=(0x0008, 0x0032)),
    ]


def main_make_mods():
    """
    Exercise header modification code to make example data we can use.

    We can confirm changes are made from shell using AFNI's ``dicom_hinfo``

    .. code-block:: sh

        find example/dicom/mod* -iname 'MR*' -exec dicom_hinfo -tag 0010,0010 -sepstr $'\\t' -last {} \\+

        #   mod1 example/dicom/mod1/HabitTask/MR.1.3.12.2.1107.5.2.43.167046.2022122209214150118864465
        #   mod1 example/dicom/mod1/HabitTask/MR.1.3.12.2.1107.5.2.43.167046.2022122209214176799264617
        #   mod2 example/dicom/mod2/HabitTask/MR.1.3.12.2.1107.5.2.43.167046.2022122209214150118864465
        #   mod2 example/dicom/mod2/HabitTask/MR.1.3.12.2.1107.5.2.43.167046.2022122209214176799264617

    """

    new_tags_mod1 = (
        [pydicom.DataElement(value="1301", VR="DS", tag=(0x0018, 0x0080))]
        + gen_ids("mod1")
        + gen_acqdates()
        + gen_anon()
    )

    # change Series Number
    new_series = [pydicom.DataElement(value="2", VR="IS", tag=(0x0020, 0x0011))]
    change_tags(
        Path("example_dicoms/RewardedAnti_good.dcm"),
        new_tags_mod1 + new_series,
        Path("example_dicoms/RewardedAnti_wrongTR.dcm"),
    )

    # change_tags(
    #    Path("example/dicom/11903_20221222/HabitTask_704x752.18/"),
    #    new_tags_mod1,
    #    Path("example/dicom/mod1/HabitTask/"),
    # )

    # new_tags_mod2 = (
    #    [pydicom.DataElement(value="1300", VR="DS", tag=(0x0018, 0x0080))]
    #    + gen_ids("mod2")
    #    + gen_acqdates()
    #    + gen_anon()

    # )

    # change_tags(
    #    Path("example/dicom/mod1/HabitTask/"),
    #    new_tags_mod2,
    #    Path("example/dicom/mod2/HabitTask/"),
    # )


if __name__ == "__main__":
    main_make_mods()
