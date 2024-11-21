#!/usr/bin/env python3
import pytest

from dcmmeta2tsv import DicomTagReader, TagDicts


def test_newlinecomment():
    dtr = DicomTagReader()
    dcm_path = "example_dicoms/B1Map_newline.dcm"
    all_tags = dtr.read_dicom_tags(dcm_path)
    assert (
        all_tags["Comments"] == "Flip Angle map (unit: 0.1 degree) B0 correction: OFF"
    )
