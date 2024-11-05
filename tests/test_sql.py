#!/usr/bin/env python3
import sqlite3

import pytest

from acq2sqlite import DBQuery
from dcmmeta2tsv import DicomTagReader, TagDicts
from template_checker import TemplateChecker


@pytest.fixture
def db():
    """create an in memory database handler"""
    mem_db = DBQuery(sqlite3.connect(":memory:"))
    with open("schema.sql") as f:
        _ = [mem_db.sql.execute(c) for c in f.read().split(";")]
    mem_db.sql.commit()
    return mem_db


@pytest.fixture
def good_dcm_dict():
    """dcm dictionary for good example"""
    reader = DicomTagReader()
    f = "example_dicoms/RewardedAnti_good.dcm"
    return reader.read_dicom_tags(f)


def test_dict_to_db_row(db, good_dcm_dict):
    """add to db and check add"""
    db.dict_to_db_row(good_dcm_dict)
    assert db.check_acq(good_dcm_dict)


def test_template(db, good_dcm_dict):
    """add to db and check add"""
    db.dict_to_db_row(good_dcm_dict)
    with open("make_template_by_count.sql") as f:
        _ = [db.sql.execute(c) for c in f.read().split(";")]

    tmpl = db.get_template(good_dcm_dict["Project"], good_dcm_dict["SequenceName"])
    assert int(tmpl["TR"]) == int(good_dcm_dict["TR"])
