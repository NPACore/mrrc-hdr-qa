#!/usr/bin/env python3
import sqlite3
from pathlib import Path

import pytest

from mrqart.seq_report import render_seq_report

PROJECT = "Brain^WPC-8409"
SUBID = "20260206Sarpal1"
SEQ = "BoleroSlc15Fov216_thk3mm_tra"


@pytest.fixture
def mem_sql(tmp_path):
    """
    Create an in-memory DB that matches the project's schema,
    plus a template_by_count table.
    """
    sql = sqlite3.connect(":memory:")
    sql.row_factory = sqlite3.Row

    # Load schema.sql from repo root (tests/ is one level down)
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    schema_txt = schema_path.read_text()

    # Execute each statement
    for stmt in schema_txt.split(";"):
        s = stmt.strip()
        if s:
            sql.execute(s)

    sql.execute(
        """
        create table template_by_count (
            n int, Project text, SequenceName text,
            param_id int, first text, last text
        )
        """
    )

    return sql


def _insert_acq_param(sql: sqlite3.Connection, **cols) -> int:
    """
    Insert a row into acq_param with only the provided columns.
    Returns the inserted rowid.
    """
    keys = list(cols.keys())
    vals = [cols[k] for k in keys]
    qs = ",".join(["?"] * len(vals))
    sql.execute(f"INSERT INTO acq_param ({','.join(keys)}) VALUES ({qs})", vals)
    return int(sql.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_acq(
    sql: sqlite3.Connection,
    *,
    param_id: int,
    acqdate: str,
    acqtime: str,
    station: str,
    subid: str,
    series: int,
):
    sql.execute(
        """
        INSERT INTO acq (param_id, AcqDate, AcqTime, Station, SubID, SeriesNumber)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (param_id, acqdate, acqtime, station, subid, str(series)),
    )


def test_seq_report_te_mismatch_sorted_values(mem_sql, tmp_path):
    sql = mem_sql

    tmpl_param_id = _insert_acq_param(
        sql,
        Project=PROJECT,
        SequenceName=SEQ,
        SequenceType="fm2d3",
        TR="220",
        TE="5",
        FA="20",
        TA="TA 46.86",
        FoV="FoV 216*216",
        Matrix="[72, 0, 0, 72]",
        PixelResol="[3, 3]",
        BWP="1005",
        Phase="1",
        PED_major="COL",
        Comments="null",
    )

    sql.execute(
        """
        INSERT INTO template_by_count (n, Project, SequenceName, param_id, first, last)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (37, PROJECT, SEQ, tmpl_param_id, "20250425", "20260206"),
    )

    # ---- four acq rows for that subject:
    # TE alternates between 5 and 12 (so 2/4 mismatch)
    param_te5 = _insert_acq_param(
        sql,
        Project=PROJECT,
        SequenceName=SEQ,
        SequenceType="fm2d3",
        TR="220",
        TE="5",
        FA="20",
        TA="TA 46.86",
        FoV="FoV 216*216",
        Matrix="[72, 0, 0, 72]",
        PixelResol="[3, 3]",
        BWP="1005",
        Phase="1",
        PED_major="COL",
        Comments="null",
    )
    param_te12 = _insert_acq_param(
        sql,
        Project=PROJECT,
        SequenceName=SEQ,
        SequenceType="fm2d3",
        TR="220",
        TE="12",
        FA="20",
        TA="TA 46.86",
        FoV="FoV 216*216",
        Matrix="[72, 0, 0, 72]",
        PixelResol="[3, 3]",
        BWP="1005",
        Phase="1",
        PED_major="COL",
        Comments="null",
    )

    _insert_acq(
        sql,
        param_id=param_te5,
        acqdate="20260206",
        acqtime="164031.950000",
        station="AWP18914 pTX",
        subid=SUBID,
        series=13,
    )
    _insert_acq(
        sql,
        param_id=param_te12,
        acqdate="20260206",
        acqtime="164032.177500",
        station="AWP18914 pTX",
        subid=SUBID,
        series=12,
    )
    _insert_acq(
        sql,
        param_id=param_te5,
        acqdate="20260206",
        acqtime="164328.112500",
        station="AWP18914 pTX",
        subid=SUBID,
        series=15,
    )
    _insert_acq(
        sql,
        param_id=param_te12,
        acqdate="20260206",
        acqtime="164328.340000",
        station="AWP18914 pTX",
        subid=SUBID,
        series=14,
    )

    sql.commit()

    db_path = tmp_path / "db.sqlite"
    disk = sqlite3.connect(str(db_path))
    sql.backup(disk)
    disk.close()

    report = render_seq_report(
        project=PROJECT,
        subid=SUBID,
        seqname=SEQ,
        db_path=db_path,
        marquee_cols=["TE"],
        examples=0,
    )

    assert "MRQART per-sequence summary" in report
    assert f"Project:  {PROJECT}" in report
    assert f"Sequence: {SEQ}" in report
    assert f"SubID:    {SUBID}" in report
    assert "Rows matched: 4" in report
    assert "Template (from template_by_count):" in report
    assert "TE: 5" in report

    # Key behavior: values are sorted so it says "saw 5, 12"
    assert "* TE: expected 5, saw 12" in report
    assert "(2/4 rows mismatched)" in report
    assert "series examples: 12, 14" in report

    # examples=0 should not print examples section
    assert "Examples (first" not in report


def test_seq_report_examples_flag(mem_sql, tmp_path):
    sql = mem_sql

    tmpl_param_id = _insert_acq_param(
        sql,
        Project=PROJECT,
        SequenceName=SEQ,
        SequenceType="fm2d3",
        TR="220",
        TE="5",
    )
    sql.execute(
        """
        INSERT INTO template_by_count (n, Project, SequenceName, param_id, first, last)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, PROJECT, SEQ, tmpl_param_id, "20250425", "20260206"),
    )

    # One row is enough for this behavior test
    param_id = _insert_acq_param(
        sql, Project=PROJECT, SequenceName=SEQ, SequenceType="fm2d3", TR="220", TE="5"
    )
    _insert_acq(
        sql,
        param_id=param_id,
        acqdate="20260206",
        acqtime="164031.950000",
        station="AWP18914 pTX",
        subid=SUBID,
        series=13,
    )
    sql.commit()

    db_path = tmp_path / "db.sqlite"
    disk = sqlite3.connect(str(db_path))
    sql.backup(disk)
    disk.close()

    report = render_seq_report(
        project=PROJECT,
        subid=SUBID,
        seqname=SEQ,
        db_path=db_path,
        marquee_cols=["TE"],
        examples=1,
    )

    assert "Examples (first 1 rows):" in report
    assert "AWP18914 pTX" in report
    assert "Series=13" in report
