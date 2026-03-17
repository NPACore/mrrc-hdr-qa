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


def test_find_errors_te_single():
    """single TE matches template exactly"""
    errors = find_errors({"TE": "38.76"}, {"TE": "38.76"})
    assert not errors


def test_find_errors_te_multiecho_match():
    """multiecho TE passes if template TE is one of the values"""
    errors = find_errors({"TE": "38.76"}, {"TE": "4.8, 38.76"})
    assert not errors


def test_find_errors_te_multiecho_no_match():
    """multiecho TE fails if template TE is not in the list"""
    errors = find_errors({"TE": "38.76"}, {"TE": "4.8,7.4"})
    assert errors["TE"]["expect"] == "38.76"
    assert errors["TE"]["have"] == "4.8,7.4"


def test_find_errors_te_wrong():
    """wrong single TE still fails"""
    errors = find_errors({"TE": "38.76"}, {"TE": "14.6"})
    assert errors["TE"]["have"] == "14.6"
