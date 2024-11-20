#!/usr/bin/env python3
"""
Convert ``db.txt`` into a sqlite database.
"""
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Optional

from dcmmeta2tsv import NULLVAL, TagValues

logging.basicConfig(level=os.environ.get("LOGLEVEL", logging.INFO))


def column_names():
    """
    These names match what's used by dcmmeta2tsv.py and 00_build_db.bash
    CSA first, normal dicom headers, and then filename.

    Defaults to reading from ``taglist.txt``
    This provides a language agnostic lookup for columns in ``schema.sql``


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

    # final file name column also not in taglist.txt (not a tag)
    tag_colnames += ["filename"]
    return tag_colnames


class DBQuery:
    """
    Convenient SQL queries for tracking dicom headers/metadata.

    This class is a poorly implemented, ad-hoc/bespoke ORM for database defined in ``schema.sql``
    """

    #: :py:data:`CONSTS` is a list of expected aquisition-invarient parameters.
    #: The values of these attributes should be the same for every acquisition
    #: sharing a ``Project × SequenceName`` pair (across all sessions of a Project).
    #:
    #: We consider the acquisition to have a Quallity Assurance error
    #: when the value of any of these parameters in a single acquisition
    #: fails to match the template.
    #:
    #: For example ``TR`` for task EPI acquisition identified by
    #: ``SequenceName=RewardedAnti`` in ``Project=WPC-8620``
    #: should always be ``1300`` ms.
    #:
    #: .. image:: ../../sphinx/imgs/nonconforming_example.png
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
        self.sql.row_factory = sqlite3.Row

        ### SQL queries
        # These are the header values (now sql columns) that should be consistent for an acquisition ('SequenceName') in a specific study ('Project')
        # So hopefully, they already exist and we can select them
        self.find_cmd = "select rowid from acq_param where " + " and ".join(
            [f"{col} = ?" for col in self.CONSTS]
        )

        # otherwise we'll need to create a new row
        consts_ins_string = ",".join(self.CONSTS)
        val_quests = ",".join(["?" for _ in self.CONSTS])
        self.sql_cmd = (
            f"INSERT INTO acq_param({consts_ins_string}) VALUES({val_quests});"
        )

        ## we'll do the same thing for the acquisition parameters
        # (e.g. time and series number)
        # that change very time.
        #  only add if not already in the DB
        acq_uniq_col = set(self.all_columns) - set(self.CONSTS) - set(["filename"])
        assert acq_uniq_col == set(
            [
                "AcqTime",
                "AcqDate",
                "SeriesNumber",
                "SubID",
                "Operator",
                "Shims",
                "Station",
            ]
        )
        # TODO: include station?

        self.find_acq = "select rowid from acq where AcqTime like ? and AcqDate like ? and SubID = ? and SeriesNumber = ?"
        self.acq_insert_columns = ["param_id"] + list(acq_uniq_col)
        acq_col_csv = ",".join(self.acq_insert_columns)
        acq_q = ",".join(["?" for _ in self.acq_insert_columns])
        self.acq_insert = f"INSERT INTO acq({acq_col_csv}) VALUES({acq_q});"

    def check_acq(self, d: TagValues) -> bool:
        """
        Is this exact acquisition (time, id, series) already in the database?

        :param d: All parameters of an acquisition
        :return: True/False if dict params exist
        """
        acq_search_vals = [
            str(x) for x in [d["AcqTime"], d["AcqDate"], d["SubID"], d["SeriesNumber"]]
        ]
        cur = self.sql.execute(self.find_acq, acq_search_vals)
        acq = cur.fetchone()
        if acq:
            logging.info("have acq %s %s", acq[0], acq_search_vals)
            return True
        return False

    def search_acq_param(self, d: TagValues) -> Optional[int]:
        """
        Try to find ``aca_param`` row id of :py:data:`CONSTS` part of input d

        :param d: dictionary of tag values (keys in CONSTS)
        :return: rowid of matching (``param_id``) or None
        """

        rowid = None
        val_array = [str(d.get(k, NULLVAL.value)) for k in self.CONSTS]
        logging.debug("searching: %s", val_array)
        cur = self.sql.execute(self.find_cmd, val_array)
        res = cur.fetchone()
        if res:
            rowid = res[0]
        return rowid

    def param_rowid(self, d: TagValues) -> Optional[int]:
        """
        :param d: dicom headers
        :return: ``acq_param`` (new or existing) rowid identifying unique set of :py:data:`CONSTS`

        Find or insert the combination of parameters for an acquisition.
        Using :py:data:`CONSTS`, the header parameters that should be invariant
        across acquisitions of the same name within a study.

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
        >>> str(db.param_rowid({}))
        'None'
        """
        if d.get("Project") is None:
            logging.warning("input dicom header has no 'Project' key!? %s", d)
            return None

        rowid = self.search_acq_param(d)
        if rowid is not None:
            logging.debug("seq repeated: found exiting %d", rowid)
        else:
            val_array = [str(d.get(k, NULLVAL.value)) for k in self.CONSTS]
            cur = self.sql.execute(self.sql_cmd, val_array)
            rowid = cur.lastrowid
            logging.info(
                "new seq param set created %d: %s %s",
                rowid,
                d.get("Project"),
                d.get("SequenceName"),
            )

        return rowid

    def dict_to_db_row(self, d: TagValues) -> None:
        """
        insert a dicom header (representative of acquisition) into db
        """
        # order here needs to match find_acq.
        if self.check_acq(d):
            return

        rowid = self.param_rowid(d)
        if not rowid:
            return
        ###
        d["param_id"] = rowid
        acq_insert_vals = [str(d[k]) for k in self.acq_insert_columns]
        cur = self.sql.execute(self.acq_insert, acq_insert_vals)
        logging.debug("new acq created: %d", cur.lastrowid)

    def tsv_to_dict(self, line: str) -> TagValues:
        """
        Read a tsv line into dictionary.

        :param line: tab separated string. likely line from ``dcmmeta2tsv.py``
        :return: dictionary with taglist.txt names and acquisition values.
        """
        vals = line.split("\t")
        return dict(zip(self.all_columns, vals))

    def is_template(self, param_id: int) -> bool:
        """
        Check if param id is the ideal template.
        """
        cur = self.sql.execute(
            "select * from template_by_count where param_id = ?", str(param_id)
        )
        res = cur.fetchone()
        if not res:
            return False
        if res[0]:
            return True
        return False

    def get_template(self, pname: str, seqname: str) -> sqlite3.Row:
        """
        Find the template from ``template_by_count``. See ``make_template_by_count.sql``

        :param pname: protocol name
        :param sqname: sequence name
        :returns: template row matching prot+seq name pair
        """
        cur = self.sql.execute(
            """
            select * from template_by_count t
            join acq_param p on t.param_id = p.rowid
            where t.Project like ? and t.SequenceName like ?
            """,
            (pname, seqname),
        )
        res = cur.fetchone()
        logging.debug("found template: %s", res)
        return res

    def find_acquisitions_since(self, since_date: Optional[str] = None):
        """
        Retrieve all acquisitions with AcqDate greater than the specified date.

        :param since_date: Date string in 'YYYY-MM-DD' format; defaults to yesterday if None.
        :return: List of acquisition rows with AcqDate > since_date.
        """

        # Default to yesterday if since_date is None
        if since_date is None:
            since_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        query = "select * from acq where AcqDate > ?"
        logging.info("Finding acquisitions since %s", since_date)

        cur = self.sql.execute(query, (since_date,))
        return cur.fetchall()


def have_pipe_data():
    return os.isatty(sys.stdout.fileno())


if __name__ == "__main__":
    db = DBQuery()
    with sys.stdin if have_pipe_data() else open("db.txt", "r") as f:
        while line := f.readline():
            d = db.tsv_to_dict(line)
            db.dict_to_db_row(d)

    db.sql.commit()
