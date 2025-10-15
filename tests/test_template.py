#!/usr/bin/env python3
import pytest
from mrqart.template_checker import TemplateChecker, find_errors


def test_find_errors_tr():
    """
    remove decimal from TR
    """
    errors = find_errors({"TR": "1300"}, {"TR": "1300.0"})
    assert not errors

    errors = find_errors({"TR": "1300"}, {"TR": "0.0"})
    assert errors["TR"]["have"] == "0.0"
    assert errors["TR"]["expect"] == "1300"


def test_find_errors_okay_null():
    """
    FoV and TA are null in siemens ICE "realtime" dicoms
    """
    errors = find_errors({"TR": "1300"}, {"TR": "null"}, allow_null=["TR"])
    assert not errors

    errors = find_errors({"TR": "1300"}, {"TR": "0.0"}, allow_null=["TR"])
    assert errors["TR"]["have"] == "0.0"
    assert errors["TR"]["expect"] == "1300"
