#!/usr/bin/env python3
"""
convert db.txt into a sqlite database
"""
import sqlite3
import logging
import re
import os
import sys
logging.basicConfig(level=logging.INFO)


def column_names():
    """
    These names match what's used by dcmmeta2tsv.py and 00_build_db.bash
    CSA first, normal dicom headers, and then filename.

    Defaults to reading from ``taglist.txt`` 
    This provides a language agnostic lookup for columns in ``schema.sql``

    AND
     *  prepends Phase and iPAT
     *  appends filename

    These column names should match what is output by
    ``./dcmmeta2tsv.bash`` or ``./dcmmeta2tsv.py``

    Also see :py:func:`dcmmeta2tsv.read_known_tags`

    >>> cn = column_names() # reads taglist.txt
    >>> cn[0] # hard coded here
    'Phase'
    >>> cn[3] # from taglist.xt
    'AcqDate'
    """
    with open("taglist.txt", "r") as f:
        tag_colnames = [
            line.split("\t")[0]
            for line in f.readlines()
            if not re.search("^name|^#", line)
        ]

    # CSA col names from 00_build_db.bash not in taglist.txt
    colnames = ["Phase", "iPAT"]
    colnames += tag_colnames
    # final file name column also not in taglist.txt (not a tag)
    colnames += [ "filename" ]
    return colnames

class DBQuery:
    """
    Convient SQL queries for tracking dicom headers/metadata
    
    Poorly implemented, ad-hoc bespoke ORM for ``schema.sql``
    """
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

    def __init__(self, sql=None):
        """
        Do a bunch of the query building up front:
          * find existing ``acq``
          * find existing ``acq_param``
          * insert new into ``acq``
          * insert new into ``acq_param``

        """
        self.all_columns = column_names()
        if sql:
            self.sql = sql
        else:
            self.sql = sqlite3.connect("db.sqlite")  # see schema.sql

        ### SQL queries
        # These are the header values (now sql columns) that should be consistant for an acquistion ('SequenceName') in a specific study ('Project')
        # So hopefully, they already exist and we can select them
        self.find_cmd = "select rowid from acq_param where " + " and ".join(
            [f"{col} = ?" for col in self.CONSTS]
        )

        # otherwise we'll need to create a new row
        consts_ins_string = ",".join(self.CONSTS)
        val_quests = ",".join(["?" for _ in self.CONSTS])
        self.sql_cmd = f"INSERT INTO acq_param({consts_ins_string}) VALUES({val_quests});"

        ## we'll do the same thing for the acquisition paramaters
        # (e.g. time and series number)
        # that change very time.
        #  only add if not already in the DB
        acq_uniq_col = set(self.all_columns) - set(self.CONSTS) - set(["filename"])
        assert acq_uniq_col == set(["AcqTime", "AcqDate", "SeriesNumber", "SubID", "Operator"])
        # TODO: include station?

        self.find_acq = "select rowid from acq where AcqTime like ? and AcqDate like ? and SubID = ? and SeriesNumber = ?"
        self.acq_insert_columns = ["param_id"] + list(acq_uniq_col)
        acq_col_csv = ','.join(self.acq_insert_columns)
        acq_q = ','.join(['?' for _ in self.acq_insert_columns])
        self.acq_insert = f"INSERT INTO acq({acq_col_csv}) VALUES({acq_q});"

    def check_acq(self, d):
        """
        Is this exact acquisition (time, id, series) already in the database?
        """
        acq_search_vals = (d["AcqTime"], d["AcqDate"], d["SubID"], d["SeriesNumber"])
        cur = self.sql.execute(self.find_acq, acq_search_vals)
        acq = cur.fetchone()
        if acq:
            logging.debug(f"have acq {acq[0]} {acq_search_vals}")
            return True
        return False

    def param_rowid(self, d):
        """
        Find or insert the combination of parameters for an aquisition.
        Using ``CONSTS``, the header parameters that should be invarient
        across acquistions of the same name within a study.

        >>> db = DBQuery(sqlite3.connect(':memory:'))
        >>> with open('schema.sql') as f: _ = [db.sql.execute(c) for c in f.read().split(";")]
        ...
        >>> # db.sql.execute(".read schema.sql")
        >>> example = {k: 'x' for k in db.CONSTS}
        >>> db.param_rowid(example)
        1
        >>> db.param_rowid(example)
        1
        >>> db.param_rowid({**example, 'Project': 'b'})
        2
        """
        val_array = [d.get(k) for k in self.CONSTS]
        logging.debug("searching: %s", val_array)
        cur = self.sql.execute(self.find_cmd, val_array)
        res = cur.fetchone()
        if res:
            rowid = res[0]
            logging.debug("seq repeated: found exiting %d", rowid)
        else:
            cur = self.sql.execute(self.sql_cmd, val_array)
            rowid = cur.lastrowid
            logging.info("new seq param set created %d: %s %s", rowid, d["Project"], d["SequenceName"])

        return rowid


    def dict_to_db_row(self, d):
        """
        insert a dicom header (representive of acquistion) into db
        """
        # order here needs to match find_acq.
        if self.check_acq(d):
            return

        rowid = self.param_rowid(d)
        ###
        d["param_id"] = rowid
        acq_insert_vals = [d[k] for k in self.acq_insert_columns]
        cur = self.sql.execute(self.acq_insert, acq_insert_vals)
        logging.debug("new acq created: %d", cur.lastrowid)

def have_pipe_data():
    return os.isatty(sys.stdout.fileno())

if __name__ == "__main__":
    db = DBQuery()
    with sys.stdin if have_pipe_data() else open("db.txt", "r") as f:
        while line := f.readline():
            vals = line.split("\t")
            d = dict(zip(db.all_columns, vals))
            db.dict_to_db_row(d)

    db.sql.commit()
