#!/usr/bin/env python3
import sqlite3

import pytest

from acq2sqlite import DBQuery
from dcmmeta2tsv import DicomTagReader, TagDicts
from template_checker import TemplateChecker
from datetime import datetime, timedelta

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

def test_find_acquisitions_since(db):
    """Test the find_acquisitions_since function with different dates"""

    # Insert test data
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    day_before_yesterday = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')

    test_data = [
        {"param_id": 1, "AcqTime": "10:00", "AcqDate": day_before_yesterday, "SeriesNumber": "001", "SubID": "SUB1", "Operator": "OP1"},
        {"param_id": 2, "AcqTime": "11:00", "AcqDate": yesterday, "SeriesNumber": "002", "SubID": "SUB2", "Operator": "OP2"},
        {"param_id": 3, "AcqTime": "12:00", "AcqDate": today, "SeriesNumber": "003", "SubID": "SUB3", "Operator": "OP3"},
    ]

    for data in test_data:
        db.sql.execute(
            "INSERT INTO acq (param_id, AcqTime, AcqDate, SeriesNumber, SubID, Operator) VALUES (?, ?, ?, ?, ?, ?)",
            (data["param_id"], data["AcqTime"], data["AcqDate"], data["SeriesNumber"], data["SubID"], data["Operator"])
        )
    db.sql.commit()
    
    # Test with yesterday's date (should return today's data)
    results_yesterday = db.find_acquisitions_since(yesterday)
    results_yesterday = [tuple(row) for row in results_yesterday]
    assert results_yesterday == [(3, '12:00', today, '003', 'SUB3', 'OP3')]

    # Test with today's date (should return no rows since there's no future data)
    results_today = db.find_acquisitions_since(today)
    results_today = [tuple(row) for row in results_today]
    assert results_today == []

    # Test with a date far in the past (should return all rows)
    results_past = db.find_acquisitions_since("2000-01-01")
    results_past = [tuple(row) for row in results_past]
    assert results_past == [
            (1, '10:00', day_before_yesterday, '001', 'SUB1', 'OP1'),
            (2, '11:00', yesterday, '002', 'SUB2', 'OP2'),
            (3, '12:00', today, '003', 'SUB3', 'OP3')
    ]

    # Test with no date (should default to yesterday and return today's date
    results_default = db.find_acquisitions_since()
    results_default = [tuple(row) for row in results_default]
    assert results_default == [(3, '12:00', today, '003', 'SUB3','OP3')]

@pytest.fixture
def template_checker():
    return TemplateChecker()

def test_check_row(template_checker, mocker):
    # Mock the template return by DBQuery.get_template
    mock_template = {
            "Project": "Brain^wpc-8620",
            "SequenceName": "HabitTask",
            "TR": "1300",
            "TE": "30",
            "FA": "60",
            "iPAT": "GRAPPA",
            "Comments": "Unaliased MB3/PE4/LB SENSE1",
            # Other relevant fields can be added as well if seen as necessary
    }

    # Mock the get_template method to return the mock_template
    mocker.patch.object(template_checker.db, 'get_template', return_value=mock_template)

    # Example row from SQL query with some values differing from the template
    test_row = {
            "Project": "Brain^wpc-8620",
            "SequenceName": "HabitTask",
            "TR": "1301", # Should trigger and error
            "TE": "30",
            "FA": "60",
            "iPAT": "GRAPPA",
            "Comments": "Unaliased MB3/PE4/LB SENSE1",

    }

    # Run the check_row function
    result: CheckResult = template_checker.check_row(test_row)

    # Expected result
    expected_errors = {
            "TR": {"expect": "1300", "have": "1301"},
    }

    # Assertions
    assert result["conforms"] == False # Should not conform due to mismatch in "TR"
    assert result["errors"] == expected_errors
    assert result["input"] == test_row
    assert result["template"] == mock_template

    # Check that get_template was called with the correct arguments
    template_checker.db.get_template.assert_called_once_with("Brain^wpc-8620", "HabitTask")
