#!/usr/bin/env python3
"""
convert db.txt into a sqlite database
"""
import sqlite3
import re


def column_names():
    """
    These names match what's used by dcmmeta2tsv.py and 00_build_db.bash
    CSA first, normal dicom headers, and then filename
    """
    # CSA col names from 00_build_db.bash not in taglist.txt
    colnames = ["Phase", "iPAT"]
    with open("taglist.txt", "r") as f:
        tag_colnames = [
            line.split("\t")[0]
            for line in f.readlines()
            if not re.search("^name|^#", line)
        ]
    colnames += tag_colnames
    colnames += [
        "filename"
    ]  # final file name column also not in taglist.txt (not a tag)
    return colnames


COLNAMES = column_names()

### SQL queries
# These are the header values (now sql columns) that should be consistant for an acquistion ('SequenceName') in a specific study ('Project')
CONSTS = [
    "Project",
    "SequenceName",
    "iPAT",
    "Comments",
    "SequenceType",
    "PED_major",
    "Phase",
    "TR",
    "TE",
    "Matrix",
    "PixelResol",
    "BWP",
    "BWPPE",
    "FA",
    "TA",
    "FoV",
]

# So hopefully, they already exist and we can select them
find_cmd = "select rowid from acq_param where " + " and ".join(
    [f"{col} = ?" for col in CONSTS]
)

# otherwise we'll need to create a new row
consts_ins_string = ",".join(CONSTS)
val_quests = ",".join(["?" for _ in CONSTS])
sql_cmd = f"INSERT INTO acq_param({consts_ins_string}) VALUES({val_quests});"

## we'll do the same thing for the acquisition paramaters (e.g. time and series number) that change very time -- only add if not already in the DB


ACQUNIQ = set(COLNAMES) - set(CONSTS) - set(["filename"])
assert ACQUNIQ == set(["AcqTime", "AcqDate", "SeriesNumber", "SubID", "Operator"])
# TODO: include station?

find_acq = "select rowid from acq where AcqTime like ? and AcqDate like ? and SubID = ? and SeriesNumber = ?"
acq_insert_columns = ["param_id"] + list(ACQUNIQ)
acq_insert = f"INSERT INTO acq({','.join(acq_insert_columns)}) VALUES({','.join(['?' for _ in acq_insert_columns])});"


def dict_to_db_row(d, sql):
    """
    insert a dicom header (representive of acquistion) into db
    """
    # order here needs to match find_acq.
    acq_search_vals = (d["AcqTime"], d["AcqDate"], d["SubID"], d["SeriesNumber"])
    cur = sql.execute(find_acq, acq_search_vals)
    acq = cur.fetchone()
    if acq:
        print(f"have acq {acq[0]} {acq_search_vals}")
        return

    val_array = [d[k] for k in CONSTS]
    print(f"searching: {val_array}")
    cur = sql.execute(find_cmd, val_array)
    res = cur.fetchone()
    if res:
        rowid = res[0]
        print(f"seq repeated: found exiting {rowid}")
    else:
        cur = sql.execute(sql_cmd, val_array)
        rowid = cur.lastrowid
        print(f"new seq: created {rowid}")
    ###
    d["param_id"] = rowid
    acq_insert_vals = [d[k] for k in acq_insert_columns]
    cur = sql.execute(acq_insert, acq_insert_vals)
    print(f"new acq: created {cur.lastrowid}")


if __name__ == "__main__":
    sql = sqlite3.connect("db.sqlite")  # see schema.sql
    with open("db.txt", "r") as f:
        while line := f.readline():
            vals = line.split("\t")
            d = dict(zip(COLNAMES, vals))
            dict_to_db_row(d, sql)

    sql.commit()
