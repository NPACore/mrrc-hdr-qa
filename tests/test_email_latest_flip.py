#!/usr/bin/env python3
"""
Tests for mrqart/email_latest_flip.py

These are designed to be:
- safe (no real mail sent)
- mostly unit / core-logic focused
- light sqlite integration where useful (in-memory DB)
"""

import sqlite3
from datetime import datetime

import pytest

from mrqart.email_latest_flip import (
    Totals,
    build_email,
    compact_error_keys,
    evaluate_rows,
    fetch_acquisitions,
    first_seen_date_for_seq,
    first_seen_from_template_by_count,
    format_expected_got,
    format_series_003,
    get_report_date,
    is_interesting_sequence_with_blacklist,
    parse_ta_seconds,
    select_eligible_rows,
    series_is_posthoc,
    study_has_any_templates,
    SeqSummary,
)


# -----------------------------
# Pure helper tests (no DB)
# -----------------------------
def test_get_report_date_default_yesterday():
    env = {}
    now = datetime(2026, 2, 10, 12, 0, 0)
    rd = get_report_date(env, now=now)
    assert rd.yday_str == "20260209"
    assert rd.date_label == "2026-02-09"


def test_get_report_date_override_yyyymmdd():
    env = {"MRQART_DATE": "20260206"}
    rd = get_report_date(env, now=datetime(2026, 2, 10, 12, 0, 0))
    assert rd.yday_str == "20260206"
    assert rd.date_label == "2026-02-06"


def test_get_report_date_override_iso():
    env = {"MRQART_DATE": "2026-02-06"}
    rd = get_report_date(env, now=datetime(2026, 2, 10, 12, 0, 0))
    assert rd.yday_str == "20260206"
    assert rd.date_label == "2026-02-06"


def test_parse_ta_seconds():
    assert parse_ta_seconds("TA 08:24") == 8 * 60 + 24
    assert parse_ta_seconds("08:24") == 8 * 60 + 24
    assert parse_ta_seconds("01:02:03") == 1 * 3600 + 2 * 60 + 3
    assert parse_ta_seconds("") is None
    assert parse_ta_seconds(None) is None
    assert parse_ta_seconds("banana") is None


def test_format_expected_got_ta_delta():
    s = format_expected_got("TA", "TA 08:24", "TA 11:15")
    assert "TA:" in s
    assert "(+171s)" in s  # 11:15 - 08:24 = 171 seconds


def test_format_expected_got_fa_delta():
    s = format_expected_got("FA", "60", "70")
    assert "FA:" in s
    assert "(+10°)" in s


def test_format_expected_got_fa_no_delta_when_equalish():
    s = format_expected_got("FA", "60.0", "60.0000000")
    assert "(+" not in s and "°" not in s  # should not show a delta


def test_series_helpers():
    assert format_series_003("9") == "009"
    assert format_series_003(12) == "012"
    assert series_is_posthoc("201") is True
    assert series_is_posthoc("200") is False
    assert series_is_posthoc("banana") is False


def test_compact_error_keys_prefers_marquee_then_ta():
    errors = {"PixelResol": {}, "TA": {}, "TE": {}, "FoV": {}}
    out = compact_error_keys(errors, prefer_cols=["TE", "TR"], max_items=6)
    # TE should come first, TA should be included early, others follow
    assert out.split(", ")[0] == "TE"
    assert "TA" in out


def test_is_interesting_sequence_with_blacklist_deny_wins():
    ok = is_interesting_sequence_with_blacklist(
        "my_localizer_scout",
        "anat_scout",
        {"interesting_substrings":["mprage"],
         "deny_substrings":["localizer"],
         "blacklist_seqtype_prefixes":["anat"],
         "disable_blacklist":False})
    assert ok is False


def test_is_interesting_sequence_with_blacklist_interesting_wins():
    ok = is_interesting_sequence_with_blacklist(
        "3DT1_mprage",
        "anat_scout",
        {"interesting_substrings":["mprage"],
        "deny_substrings":[],
        "blacklist_seqtype_prefixes":["anat"],
        "disable_blacklist":False,}
    )
    assert ok is True


def test_is_interesting_sequence_with_blacklist_disable_includes():
    ok = is_interesting_sequence_with_blacklist(
        "whatever",
        "anat_scout",
        {"interesting_substrings":[],
        "deny_substrings":[],
        "blacklist_seqtype_prefixes":["anat"],
        "disable_blacklist":True}
    )
    assert ok is True


def test_is_interesting_sequence_with_blacklist_prefix_excludes():
    ok = is_interesting_sequence_with_blacklist(
        seqname="whatever",
        seqtype="anat_scout_extra",
        settings={"interesting_substrings":[],
         "deny_substrings":[],
         "blacklist_seqtype_prefixes":["anat"],
         "disable_blacklist":False},
    )
    assert ok is False


# -----------------------------
# Selection filter tests (dict-like rows)
# -----------------------------
def test_select_eligible_rows_counts_and_filters():
    rows = [
        {
            "Project": "Brain^X",
            "SubID": "S1",
            "SequenceName": "task_rest",
            "SequenceType": "func_bold",
            "SeriesNumber": "10",
        },
        {
            "Project": "Brain^X",
            "SubID": "S1",
            "SequenceName": "task_rest",
            "SequenceType": "func_bold",
            "SeriesNumber": "201",  # posthoc -> excluded
        },
        {
            "Project": "Brain^X",
            "SubID": "S1",
            "SequenceName": "localizer_foo",
            "SequenceType": "anat_scout",
            "SeriesNumber": "11",  # denied -> excluded
        },
        {
            "Project": "7TBP^X", # ingore regexp
            "SubID": "S1SKIPME",
            "SequenceName": "localizer_foo",
            "SequenceType": "anat_scout",
            "SeriesNumber": "11",
        },
    ]

    eligible, study_counts, seq_counts, study_subids_today = select_eligible_rows(
        rows,
        {"interesting_substrings":["rest"],
         "deny_substrings": ["localizer"],
         "blacklist_study_regex": ["^7T"],
         "blacklist_prefixes":["anat"],
         "disable_blacklist":False},
    )

    assert len(eligible) == 1
    assert study_counts["Brain^X"] == 1
    assert seq_counts[("Brain^X", "S1", "task_rest")] == 1


# -----------------------------
# Core engine tests (evaluate_rows + build_email)
# -----------------------------
class StubTC:
    """
    Stub TemplateChecker.check_header. Returns dict shaped like TemplateChecker.check_header.
    Keyed by (Project, SubID, SequenceName, SeriesNumber).
    """

    def __init__(self, mapping):
        self.mapping = mapping

    def check_header(self, hdr):
        key = (
            hdr.get("Project"),
            hdr.get("SubID"),
            hdr.get("SequenceName"),
            str(hdr.get("SeriesNumber")),
        )
        # default: template exists, no diffs
        return self.mapping.get(key, {"template": {"exists": True}, "errors": {}})


def test_evaluate_rows_counts_nonconforming_anydiff_and_mia_actionable():
    marquee_cols = ["TR", "TE", "FA"]

    eligible = [
        {"Project": "Brain^A", "SubID": "S1", "SequenceName": "Seq1", "SeriesNumber": "12"},
        {"Project": "Brain^A", "SubID": "S1", "SequenceName": "Seq1", "SeriesNumber": "14"},
        {"Project": "Brain^A", "SubID": "S1", "SequenceName": "Seq1", "SeriesNumber": "15"},
        {"Project": "Brain^B", "SubID": "S2", "SequenceName": "Seq2", "SeriesNumber": "7"},
    ]

    mapping = {
        # two marquee mismatches => nonconforming + anydiff
        ("Brain^A", "S1", "Seq1", "12"): {
            "template": {"exists": True},
            "errors": {"TE": {"expect": "5", "have": "12"}},
        },
        ("Brain^A", "S1", "Seq1", "14"): {
            "template": {"exists": True},
            "errors": {"TE": {"expect": "5", "have": "12"}},
        },
        # non-marquee mismatch => anydiff only
        ("Brain^A", "S1", "Seq1", "15"): {
            "template": {"exists": True},
            "errors": {"PixelResol": {"expect": "1.0", "have": "1.1"}},
        },
        # missing template
        ("Brain^B", "S2", "Seq2", "7"): {"template": {}, "errors": {}},
    }
    tc = StubTC(mapping)

    # counts normally computed by select_eligible_rows()
    study_counts_today = {"Brain^A": 3, "Brain^B": 1}
    seq_counts_today = {
        ("Brain^A", "S1", "Seq1"): 3,
        ("Brain^B", "S2", "Seq2"): 1,
    }

    # stub funcs so we don't need a real sqlite connection in this test
    def study_has_templates_fn(_sql, project: str) -> bool:
        # treat Brain^B as onboarded so MIA is actionable
        return project == "Brain^B"

    def first_seen_from_templates_fn(_sql, project: str, seqname: str):
        return "2025-01-01"

    def first_seen_from_acq_fn(_sql, project: str, seqname: str):
        return "2025-02-02"

    seq_summary, missing_templates, totals = evaluate_rows(
        eligible,
        sql=None,
        tc=tc,
        marquee_cols=marquee_cols,
        study_counts_today=study_counts_today,
        seq_counts_today=seq_counts_today,
        study_has_templates_fn=study_has_templates_fn,
        first_seen_from_templates_fn=first_seen_from_templates_fn,
        first_seen_from_acq_fn=first_seen_from_acq_fn,
    )

    assert totals.total_checked == 4
    assert totals.total_anydiff == 3
    assert totals.total_nonconforming == 2
    assert totals.total_missing_templates == 1
    assert totals.mia_actionable == 1

    key_a = ("Brain^A", "S1", "Seq1")
    smry_a = seq_summary[key_a]
    assert smry_a.total == 3
    assert smry_a.anydiff == 3
    assert smry_a.nonconforming == 2
    assert len(smry_a.examples) > 0  # examples added for nonconforming

    key_b = ("Brain^B", "S2", "Seq2")
    smry_b = missing_templates[key_b]
    assert smry_b["count"] == 1
    assert smry_b["study_has_templates"] is True
    assert smry_b["first_seen"] == "2025-01-01"


def test_build_email_structure_and_subject_flags():
    totals = Totals(
        total_seen_today=4,
        total_checked=4,
        total_nonconforming=2,
        total_anydiff=3,
        total_missing_templates=1,
        mia_actionable=1,
    )
    marquee_cols = ["TR", "TE", "FA"]

    seq_summary = {("Brain^A", "S1", "Seq1"):
                   SeqSummary(key=("Brain^A", "S1", "Seq1"),
                              total=3,
                              nonconforming=2,
                              anydiff=3,
                              examples=[
                                  "Brain^A / S1 / Seq1.012 (diffs: TE)",
                                  "Brain^A / S1 / Seq1.014 (diffs: TE)",
                                  ],
                              mismatch_counts={
                                  ("TE", "5", "12"): 2,
                                  ("PixelResol", "1.0", "1.1"): 1,
                                  },
                              ),
                   }

    missing_templates = {
        ("Brain^B", "S2", "Seq2"): {
            "count": 1,
            "examples": ["Brain^B / S2 / Seq2.007"],
            "first_seen": "2025-01-01",
            "study_has_templates": True,
            "study_count_today": 1,
            "seq_count_today": 1,
        }
    }

    subject, body = build_email(
        date_label="2026-02-06",
        marquee_cols=marquee_cols,
        total_seen_today=4,
        seq_summary=seq_summary,
        missing_templates=missing_templates,
        totals=totals,
        study_subids_today={}
    )

    assert subject.startswith("[MRQA]")
    assert "❌" in subject  # since nonconforming or mia_actionable > 0
    assert "2/4" in subject  # "nonconforming/checked"
    assert "(4)" in subject  # total seen today
    assert "1 MIA" in subject

    assert "MRQART header compliance summary for 2026-02-06" in body
    assert "❌ Non-Conforming:" in body
    assert "🕳️ MIA (study has templates)" in body
    assert "ℹ️ Summary:" in body


def test_build_email_green_when_no_nonconforming_and_no_mia():
    totals = Totals(
        total_seen_today=2,
        total_checked=2,
        total_nonconforming=0,
        total_anydiff=0,
        total_missing_templates=0,
        mia_actionable=0,
    )
    subject, body = build_email(
        date_label="2026-02-06",
        marquee_cols=["TE"],
        total_seen_today=2,
        seq_summary={},
        missing_templates={},
        study_subids_today={},
        totals=totals,
    )
    assert "✅" in subject
    assert "Non-Conforming" in body
    assert "none" in body


# -----------------------------
# sqlite integration tests (in-memory)
# -----------------------------
@pytest.fixture
def mem_sql():
    sql = sqlite3.connect(":memory:")
    sql.row_factory = sqlite3.Row

    # Minimal subset of schema needed for the functions we test here.
    sql.execute(
        """
        CREATE TABLE acq_param (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            Project TEXT,
            SequenceName TEXT,
            SequenceType TEXT
        )
        """
    )
    sql.execute(
        """
        CREATE TABLE acq (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            param_id INTEGER,
            AcqDate TEXT,
            AcqTime TEXT,
            Station TEXT,
            SubID TEXT,
            SeriesNumber TEXT
        )
        """
    )
    sql.execute(
        """
        CREATE TABLE template_by_count (
            n INTEGER,
            Project TEXT,
            SequenceName TEXT,
            param_id INTEGER,
            first TEXT,
            last TEXT
        )
        """
    )
    return sql


def test_fetch_acquisitions_in_memory(mem_sql):
    # Insert params
    mem_sql.execute(
        "INSERT INTO acq_param (Project, SequenceName, SequenceType) VALUES (?,?,?)",
        ("Brain^WPC-8409", "BoleroSlc15Fov216_thk3mm_tra", "shim_misc"),
    )
    mem_sql.execute(
        "INSERT INTO acq_param (Project, SequenceName, SequenceType) VALUES (?,?,?)",
        ("Brain^WPC-8409", "WBBoleroSlc21Fov216_thk3mm_tra", "shim_misc"),
    )

    # Insert acquisitions for 20260206
    mem_sql.execute(
        "INSERT INTO acq (param_id, AcqDate, AcqTime, Station, SubID, SeriesNumber) VALUES (?,?,?,?,?,?)",
        (1, "20260206", "11:00:00", "ST01", "20260206Sarpal1", "12"),
    )
    mem_sql.execute(
        "INSERT INTO acq (param_id, AcqDate, AcqTime, Station, SubID, SeriesNumber) VALUES (?,?,?,?,?,?)",
        (1, "20260206", "11:01:00", "ST01", "20260206Sarpal1", "14"),
    )
    mem_sql.execute(
        "INSERT INTO acq (param_id, AcqDate, AcqTime, Station, SubID, SeriesNumber) VALUES (?,?,?,?,?,?)",
        (2, "20260206", "11:02:00", "ST01", "20260206Sarpal1", "4"),
    )
    mem_sql.commit()

    rows = fetch_acquisitions(mem_sql, "20260206")
    assert len(rows) == 3
    assert rows[0]["AcqDate"] == "20260206"
    assert rows[0]["Project"] == "Brain^WPC-8409"
    assert "SequenceName" in rows[0].keys()


def test_study_has_any_templates(mem_sql):
    assert study_has_any_templates(mem_sql, "Brain^X") is False
    mem_sql.execute(
        "INSERT INTO template_by_count (Project, SequenceName, param_id, first, last, n) VALUES (?,?,?,?,?,?)",
        ("Brain^X", "Seq", 1, "20260101", "20260201", 10),
    )
    mem_sql.commit()
    assert study_has_any_templates(mem_sql, "Brain^X") is True


def test_first_seen_from_template_by_count(mem_sql):
    mem_sql.execute(
        "INSERT INTO template_by_count (Project, SequenceName, param_id, first, last, n) VALUES (?,?,?,?,?,?)",
        ("Brain^X", "Seq", 1, "20260101", "20260201", 10),
    )
    mem_sql.commit()
    assert first_seen_from_template_by_count(mem_sql, "Brain^X", "Seq") == "2026-01-01"


def test_first_seen_date_for_seq(mem_sql):
    # param row
    mem_sql.execute(
        "INSERT INTO acq_param (Project, SequenceName, SequenceType) VALUES (?,?,?)",
        ("Brain^X", "Seq", "func_bold"),
    )
    # acq rows across dates
    mem_sql.execute(
        "INSERT INTO acq (param_id, AcqDate, AcqTime, Station, SubID, SeriesNumber) VALUES (?,?,?,?,?,?)",
        (1, "20260201", "10:00:00", "ST01", "S1", "1"),
    )
    mem_sql.execute(
        "INSERT INTO acq (param_id, AcqDate, AcqTime, Station, SubID, SeriesNumber) VALUES (?,?,?,?,?,?)",
        (1, "20260115", "10:00:00", "ST01", "S1", "2"),
    )
    mem_sql.commit()

    # MIN(AcqDate) should become ISO
    assert first_seen_date_for_seq(mem_sql, "Brain^X", "Seq") == "2026-01-15"

