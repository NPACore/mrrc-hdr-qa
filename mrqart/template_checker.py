"""
check a header against best template
"""

import re
from typing import TypedDict

from .acq2sqlite import DBQuery
from .dcmmeta2tsv import DicomTagReader, TagKey, TagValues

#: Dictionary for mismatches in input (``have`` key) and template (``expect`` key)
ErrorCompare = TypedDict("ErrorCompare", {"have": str, "expect": str})
ErrorDict = dict[TagKey, ErrorCompare]

#: * | ``conforms``: false when a :py:data:`acq2sqlite.DBQuery.CONSTS`
#:   | template-parameter between ``input`` and ``template`` mismatch
#: * | ``errors``: nested dict of {``mismatched_param``: ``{'have':...,'expect':...}}``
#:     (parameter keyed dictionary with :py:class:`ErrorCompare` values)
#: * | ``input``: dict of all parameters of an input dicom header
#:   | (:py:class:`dcmmeta2tsv.TagValues`)
#: * | ``template``: all the parameters of a template (matching Study, SeriesName)
#:   | Also a :py:class:`dcmmeta2tsv.TagValues`
#:
#: Here's an example of :py:class:`CheckResult` datastructure in html/javascript
#: on the `static debug-enabled page <../_static/mrqart/index.html>`_
#:
#: .. image:: ../../sphinx/imgs/CheckResults_mrqart.png
#:
CheckResult = TypedDict(
    "CheckResult",
    {
        "conforms": bool,
        "input": TagValues,
        "template": TagValues,
        "errors": ErrorDict,
    },
)


def _norm_str(x) -> str:
    """
    Normalize strings for tolerant comparisons:
    - collapse whitespace runs to a single space
    - trim leading/trailing whitespace
    - case-insensitive via casefold (locale-robust)
    """
    return re.sub(r"\s+", " ", str(x)).strip().casefold()


def find_errors(
    template: TagValues, current_hdr: TagValues, allow_null: list[TagKey] = []
) -> ErrorDict:
    """
    Given a template and hdr, find any mismatches (non-conforming errors).

    :param template: expected values
    :param current_hdr: values we currently have
    :param allow_null: current keys that can be null.
                       see py:class:`TemplateChecker.context`
    :returns: dictionary of tag key names and the have/expect values

    >>> find_errors({"TR": "1300"}, {"TR": "1300"})
    {}
    >>> find_errors({"TR": "1300"}, {"TR": "2000"})
    {'TR': {'expect': '1300', 'have': '2000'}}
    >>> find_errors({"Project": "Brain^WPC-8620"}, {"Project": "Brain^wpc-8620"})
    {}
    """
    errors = {}
    for k in DBQuery.CONSTS:
        t_k = template.get(k, "null")
        h_k = current_hdr.get(k, "null")

        # ["FoV", "TA", "BWPPE"] can be null in realtime (ICE) headers
        if k in allow_null and h_k == "null":
            continue

        # Specific checks:
        if k == "TR":
            # TR is in ms; compare ints of floats to ignore decimal precision
            if t_k == "null":
                t_k = 0
            if h_k == "null":
                h_k = 0
            check = int(float(t_k)) == int(float(h_k))
        elif k == "TE":
            # multiecho: either header or template may have comma-separated TEs
            # pass if there is any overlap between the two sets
            t_values = {_norm_str(v.strip()) for v in str(t_k).split(",")}
            h_values = {_norm_str(v.strip()) for v in str(h_k).split(",")}
            check = bool(t_values & h_values)
        elif k == "iPAT":
            # Keep strict for compact tokens like 'p2'
            check = str(t_k) == str(h_k)
        else:
            # Default tolerant compare for string-like fields
            check = _norm_str(t_k) == _norm_str(h_k)

        if check:
            continue
        errors[k] = {"expect": t_k, "have": h_k}
    return errors


class TemplateChecker:
    """cache db connection and list of tags
    read a dicom file and report if it conforms to the expected template
    """

    def __init__(self, db=None, context="DB"):
        """
        db connection and tag reader (from taglist.txt)
        :param db: sql connection passed on to :py:class:`DBQuery`.
            ``None`` (default) is local sqlite3.
        :param context: where is template checker running
             * | "DB" - rigorous nightly DB check
             * | "RT" - lenient for ICEconfig realtime
               | dicoms missing some headers
        """
        self.db = DBQuery(db)
        self.reader = DicomTagReader()
        self.context = context

    def check_file(self, dcm_path) -> CheckResult:
        """
        File dispatcher for :py:func:`TemplateChecker.check_header`
        """
        hdr = self.reader.read_dicom_tags(dcm_path)
        return self.check_header(hdr)

    def check_header(self, hdr) -> CheckResult:
        """
        Check acquisition parameters against its template.
        """
        template = self.db.get_template(hdr["Project"], hdr["SequenceName"])

        allow_null = []
        if self.context == "RT":
            # FoV and TA (and sometimes BWPPE) are often missing in scanner-pushed RT dicoms
            allow_null = ["FoV", "TA", "BWPPE"]

        if template:
            template = dict(template)
            errors = find_errors(template, hdr, allow_null)
            errors = clean_rt(errors)
        else:
            template = {}
            errors = {}

            # if self.context == "RT":
            #errors = clean_rt(errors)

        return {
            "conforms": not errors,
            "errors": errors,
            "input": hdr,
            "template": template,
        }


def float_or_0(val: str) -> float:
    "float or zero"
    try:
        return float(val)
    except ValueError:
        return 0.0


def arraystr_to_float(val: str) -> list[float]:
    """
    Parse array values from different dicom types

    >>> arraystr_to_float("[1.0, 2.0]")
    [1.0, 2.0]
    >>> arraystr_to_float("1.0,2.0")
    [1.0, 2.0]
    """
    no_square = str(val).replace("[", "").replace("]", "").replace(" ", "")
    arr = [float_or_0(x) for x in no_square.split(",")]
    return arr


def fuzzy_arr_check(have, expect) -> bool:
    """
    Compare only 3 decimals of a float or array of floats.
    Used by :py:func:`clean_rt` when comparing realtime dicom headers to DB

    >>> fuzzy_arr_check('2.00001', '2')
    True
    >>> fuzzy_arr_check('[2.00001, 0.0]', '2.0,0.0000001')
    True
    >>> fuzzy_arr_check('[2,0]', '2,1')
    False
    """
    have = arraystr_to_float(have)
    expect = arraystr_to_float(expect)

    have = ",".join(["%.3f" % x for x in have])
    expect = ",".join(["%.3f" % x for x in expect])
    return have == expect


def clean_rt(errors: ErrorDict) -> ErrorDict:
    """
    Clean up errors that are not actually errors in "realtime" dicom headers.

    Currently (2025-02-26) only checks ``PixelResol`` using :py:func:`fuzzy_arr_check`
    """
    if "PixelResol" in errors.keys():
        errcmp = errors["PixelResol"]
        if fuzzy_arr_check(errcmp["have"], errcmp["expect"]):
            del errors["PixelResol"]

    return errors
