"""
check a header against best template
"""

from typing import Optional, TypedDict

from acq2sqlite import DBQuery
from dcmmeta2tsv import DicomTagReader, TagDicts, TagValues

ErrorCompare = TypedDict("ErrorCompare", {"have": str, "expect": str})
CheckResult = TypedDict(
    "CheckResult",
    {
        "conforms": bool,
        "input": TagValues,
        "template": TagValues,
        "errors": dict[str, ErrorCompare],
    },
)


def find_errors(template: TagValues, current_hdr: TagValues) -> dict[str, ErrorCompare]:
    """
    given a template and hdr, find any mismatches (non-conforming errors)
    :param template: expected values
    :param current_hdr: values we currently have
    :returns: dictionary of tag key names and the have/expect values
    """
    errors = {}
    for k in DBQuery.CONSTS:
        t_k = template.get(k, "0")
        h_k = current_hdr.get(k, "0")

        # TODO: more checks for specific headers
        #: TR is in milliseconds. no need to keep decimals precision
        if k == "TR":
            check = int(float(t_k)) == int(float(h_k))
        elif k == "iPAT":
            check = t_k == h_k
        else:
            check = str(t_k) == str(h_k)

        if check:
            continue
        errors[k] = {"expect": t_k, "have": h_k}
    return errors


class TemplateChecker:
    """cache db connection and list of tags
    read a dicom file and report if it conforms to the expected template
    """

    def __init__(self):
        """
        db connection and tag reader (from taglist.txt)
        """
        self.db = DBQuery()
        self.reader = DicomTagReader()

    def check_file(self, dcm_path) -> CheckResult:
        """
        File disbatch for :py:func:`TemplateChecker.check_header`

        :param dcm_path: path to dicom file with header/parameters to read.
        :returns: output of check_header
        """
        hdr = self.reader.read_dicom_tags(dcm_path)
        return self.check_header(hdr)

    def check_header(self, hdr) -> CheckResult:
        """
        Check acquisition parameters against it's template.

        :param hdr: DB or file dictionary desc. acq. to check against template
        :returns: conforming status, errors, and comparison information
        """
        template = self.db.get_template(hdr["Project"], hdr["SequenceName"])
        template = dict(template)

        # no template, no errors
        if template:
            errors = find_errors(template, hdr)
        else:
            errors = {}

        return {
            "conforms": not errors,
            "errors": errors,
            "input": hdr,
            "template": dict(template),
        
        }
    def check_row(self, row: dict) -> CheckResult:
        """ 
        Check a single SQL row against its template.

        :parm row: Dictionary of header parameters (a row from SQL query)
        :returns: Conforming status, errors, and comparison information.
        """

        # Retrieve the template based on Project and SequenceName in the row
        template = self.db.get_template(row["Project"], row["SequenceName"])
        template = dict(template)

        # Check for differences using find_errors
        errors = find_errors(template, row) if template else {}

        return {
                "conforms": not errors,
                "errors": errors,
                "input": row, 
                "template": template,
        }
