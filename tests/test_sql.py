#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta

import pytest

from acq2sqlite import DBQuery
from dcmmeta2tsv import DicomTagReader, TagDicts
from template_checker import CheckResult, TemplateChecker

#: Example template to test against. Previously used within test like::
#:   mocker.patch.object(template_checker.db, "get_template", return_value=mock_template)
#:
#: but this this leaks to other tests!?
#: https://github.com/pytest-dev/pytest/pull/8276/files

MOCK_TEMPLATE = {
    "Project": "Brain^wpc-8620",
    "SequenceName": "HabitTask",
    "TR": "1300",
    "TE": "30",
    "FA": "60",
    "iPAT": "GRAPPA",
    "Comments": "Unaliased MB3/PE4/LB SENSE1",
    # Other relevant fields can be added as well if seen as necessary
}


@pytest.fixture
def db():
    """create an in memory database handler"""
    mem_db = DBQuery(sqlite3.connect(":memory:"))
    with open("schema.sql") as f:
        _ = [mem_db.sql.execute(c) for c in f.read().split(";")]
    # create template table. also see ../make_template_by_count.sql
    mem_db.sql.execute(
        """
      create table template_by_count (
          n int, Project text, SequenceName text,
          param_id int, first text, last text)"""
    )
    vals = [x for x in MOCK_TEMPLATE.values()]
    cols = ",".join(MOCK_TEMPLATE.keys())
    qs = ",".join(["?" for x in vals])
    sql = f"INSERT INTO acq_param ({cols}) VALUES ({qs})"
    mem_db.sql.execute(sql, vals)
    sql = (
        "INSERT INTO template_by_count (Project, SequenceName, param_id)"
        + f"VALUES ('{MOCK_TEMPLATE['Project']}', '{MOCK_TEMPLATE['SequenceName']}', 1)"
    )
    mem_db.sql.execute(sql)

    return mem_db


@pytest.fixture
def good_dcm_dict():
    """dcm dictionary for good example"""
    reader = DicomTagReader()
    f = "example_dicoms/RewardedAnti_good.dcm"
    return reader.read_dicom_tags(f)


def test_no_add_missingvals(db):
    # expect to have at least all of these
    # TODO: maybe shouldn't die if these 4 dont exist? (needed for check_acq)
    bad_data = {
        "AcqTime": "null",
        "AcqDate": "null",
        "SubID": "null",
        "SeriesNumber": "null",
    }
    assert not db.dict_to_db_row(bad_data)


def test_dict_to_db_row(db, good_dcm_dict):
    """add to db and check add"""
    assert db.dict_to_db_row(good_dcm_dict)
    assert db.check_acq(good_dcm_dict)


def test_template(db, good_dcm_dict):
    """add to db and check add"""
    db.dict_to_db_row(good_dcm_dict)
    with open("make_template_by_count.sql") as f:
        _ = [db.sql.execute(c) for c in f.read().split(";")]

    tmpl = db.get_template(good_dcm_dict["Project"], good_dcm_dict["SequenceName"])
    assert int(tmpl["TR"]) == int(good_dcm_dict["TR"])


def test_find_acquisitions_since(db):
    """Test the find_acquisitions_since function with different dates"""

    # Insert test data
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    day_before_yesterday = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    test_data = [
        {
            "param_id": 1,
            "AcqTime": "10:00",
            "AcqDate": day_before_yesterday,
        },
        {
            "param_id": 2,
            "AcqTime": "11:00",
            "AcqDate": yesterday,
        },
        {
            "param_id": 3,
            "AcqTime": "12:00",
            "AcqDate": today,
        },
    ]

    for data in test_data:
        db.sql.execute(
            "INSERT INTO acq (param_id, AcqTime, AcqDate) VALUES (?, ?, ?)",
            (data["param_id"], data["AcqTime"], data["AcqDate"]),
        )

    # Test with yesterday's date (should return today's data)
    results_yesterday = db.find_acquisitions_since(yesterday)
    results_yesterday = [tuple(row[0:3]) for row in results_yesterday]
    assert results_yesterday == [(3, "12:00", today)]

    # Test with today's date (should return no rows since there's no future data)
    results_today = db.find_acquisitions_since(today)
    assert results_today == []

    # Test with a date far in the past (should return all rows)
    results_past = db.find_acquisitions_since("2000-01-01")
    results_past = [tuple(row[0:3]) for row in results_past]
    assert results_past == [
        (1, "10:00", day_before_yesterday),
        (2, "11:00", yesterday),
        (3, "12:00", today),
    ]

    # Test with no date (should default to yesterday and return today's date
    results_default = db.find_acquisitions_since()
    results_default = [tuple(row[0:3]) for row in results_default]
    assert results_default == [(3, "12:00", today)]


@pytest.fixture
def template_checker(db):
    return TemplateChecker(db.sql)


def test_check_header_notemplate(template_checker):
    """
    No existing template? assume conforms.
    """
    test_row = {
        "Project": "Brain^wpc-DNE",
        "SequenceName": "NoSequence",
        "TR": "1301",
        "TE": "30",
        "FA": "60",
        "iPAT": "GRAPPA",
        "Comments": "Unaliased MB3/PE4/LB SENSE1",
    }
    result = template_checker.check_header(test_row)
    assert result["errors"] == {}
    assert result["conforms"]


def test_check_header(template_checker):
    """
    Example row from SQL query with some values differing from the template
    """
    test_row = {
        "Project": "Brain^wpc-8620",
        "SequenceName": "HabitTask",
        "TR": "1301",  # Should trigger and error
        "TE": "30",
        "FA": "60",
        "iPAT": "GRAPPA",
        "Comments": "Unaliased MB3/PE4/LB SENSE1",
    }

    # Run the check_row function
    result: CheckResult = template_checker.check_header(test_row)

    # Expected result
    expected_errors = {
        "TR": {"expect": "1300", "have": "1301"},
    }

    # Assertions
    assert result["conforms"] == False  # Should not conform due to mismatch in "TR"
    assert result["errors"]["TR"] == expected_errors["TR"]
    assert result["input"] == test_row
    assert result["template"]["TR"] == MOCK_TEMPLATE["TR"]


def test_check_header_matches(template_checker):
    result: CheckResult = template_checker.check_header(MOCK_TEMPLATE)
    assert result["errors"] == {}
    assert result["conforms"] == True
