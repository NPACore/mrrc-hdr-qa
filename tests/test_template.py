#!/usr/bin/env python3
import pytest

from template_checker import TemplateChecker, find_errors


def test_find_errors_tr():
    errors = find_errors({"TR": "1300"}, {"TR": "1300.0"})
    assert not errors

    errors = find_errors({"TR": "1300"}, {"TR": "0.0"})
    assert errors["TR"]["have"] == "0.0"
    assert errors["TR"]["expect"] == "1300"
