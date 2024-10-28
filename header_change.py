#!/usr/bin/env python3
"""
Modify DICOM header information including all fields from acq_param in all DICOM files within a directory.
"""
import os
from pathlib import Path
from typing import List, Optional
import random
from datetime import datetime, timedelta
from itertools import chain
import pydicom


def change_tags_in_directory(
    dcm_dir: Path, new_data: List[pydicom.DataElement], out_dir: Optional[Path] = None
):
    """
    Change specified tags of all DICOM files in a directory.

    :param dcm_dir: Input directory with DICOM files (e.g., `MR*`, `*IMA`, or `*dcm`).
    :param new_data: List of DataElements to replace, e.g.:
        ``[pydicom.DataElement(value="new_value", VR="LO", tag=(0x0010, 0x0010))]``
    :param out_dir: Optional. Where to save modified DICOMs. If None, it overwrites the original files.
    """
    all_dicoms = chain(dcm_dir.glob("MR*"), dcm_dir.glob("*IMA"), dcm_dir.glob("*dcm"))

    for dicom_file in all_dicoms:
        dcm = pydicom.dcmread(dicom_file)
        
        print(f"Processing file: {dicom_file}")

        # Print current values for debugging before modification
        print("Before modification:")
        for datum in new_data:
            if datum.tag in dcm:
                print(f"Tag {datum.tag}: {dcm[datum.tag].value}")

        # Modify the specified tags
        for datum in new_data:
            dcm[datum.tag] = datum

        # Print new values after modification
        print("After modification:")
        for datum in new_data:
            print(f"Tag {datum.tag}: {dcm[datum.tag].value}")

        # Define where to save the modified DICOM
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            new_file = out_dir / dicom_file.name
        else:
            new_file = dicom_file

        # Save the modified DICOM file
        dcm.save_as(new_file)
        print(f"Modified DICOM saved to: {new_file}")


def gen_anon() -> List[pydicom.DataElement]:
    """
    Generate random values for Patient's Birth Date, Age, and Sex to anonymize the DICOMs.
    
    :return: List of DataElements with randomized values.
    """
    dob = f"{random.randrange(1980, 2024):04d}0101"
    age = f"{random.randrange(8, 100):03d}Y"
    sex = random.choice(["M", "F"])
    return [
        pydicom.DataElement(value=dob, VR="DA", tag=(0x0010, 0x0030)),
        pydicom.DataElement(value=age, VR="AS", tag=(0x0010, 0x1010)),
        pydicom.DataElement(value=sex, VR="CS", tag=(0x0010, 0x0040)),
    ]


def gen_ids(new_id: str) -> List[pydicom.DataElement]:
    """
    Generate DataElements for Patient's Name and ID.
    
    :param new_id: String to use for both Patient Name and Patient ID.
    :return: List of DataElements with the new ID.
    """
    return [
        pydicom.DataElement(value=new_id, VR="PN", tag=(0x0010, 0x0010)),  # Patient's Name
        pydicom.DataElement(value=new_id, VR="LO", tag=(0x0010, 0x0020)),  # Patient's ID
    ]


def gen_acq_param_tags() -> List[pydicom.DataElement]:
    """
    Generate random values for various DICOM fields related to the acq_param schema.

    :return: List of DataElements to modify fields such as TR, TE, FA, Matrix, etc.
    """
    # Generate random TR (Repetition Time) and TE (Echo Time)
    tr = f"{random.uniform(1000, 2000):.2f}"  # TR in milliseconds
    te = f"{random.uniform(10, 50):.2f}"      # TE in milliseconds

    # Generate other values for acquisition parameters
    fov = f"{random.uniform(200, 300):.2f}"   # Field of View in mm
    fa = f"{random.uniform(70, 120):.2f}"     # Flip Angle in degrees
    matrix = "256x256"                        # Matrix size example
    pixel_resol = [0.9375, 0.9375]            # Pixel resolution as list of floats
    phase_enc_dir = random.choice(["ROW", "COL"])  # Phase Encoding Direction

    return [
        pydicom.DataElement(value=tr, VR="DS", tag=(0x0018, 0x0080)),    # TR
        pydicom.DataElement(value=te, VR="DS", tag=(0x0018, 0x0081)),    # TE
        pydicom.DataElement(value=fa, VR="DS", tag=(0x0018, 0x1314)),    # Flip Angle
        pydicom.DataElement(value=matrix, VR="LO", tag=(0x0051, 0x100C)),# Matrix
        pydicom.DataElement(value=pixel_resol, VR="DS", tag=(0x0028, 0x0030)), # Pixel Resolution
        pydicom.DataElement(value=fov, VR="DS", tag=(0x0018, 0x1100)),   # Field of View
        pydicom.DataElement(value=phase_enc_dir, VR="CS", tag=(0x0018, 0x1312)), # PED_major
    
    ]


def main_loop_modify_dicoms():
    """
    Loop through a directory of DICOMs and modify their headers based on acq_param schema.
    
    In this example, all DICOMs in the directory 'dicoms/' will be modified with 
    new random acquisition parameters and anonymized patient information, and saved in 'modifiedDicoms/'.
    """
    dicom_directory = Path(os.path.expanduser("~/src/mrrc-hdr-qa/dicoms"))
    output_directory = Path(os.path.expanduser("~/src/mrrc-hdr-qa/modifiedDicoms/"))
    
    # Example new data to modify in DICOM headers
    new_tags = (
        gen_ids("modified_patient") +
        gen_acq_param_tags() +
        gen_anon()
    )

    # Modify DICOM files in the directory
    change_tags_in_directory(dicom_directory, new_tags, output_directory)


if __name__ == "__main__":
    main_loop_modify_dicoms()

