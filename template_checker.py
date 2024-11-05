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


def find_errors(template: TagValues, current_hdr: TagValues) -> dict[str,ErrorCompare]:
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
        #: TR is in milliseconds. no need to keep decimals percision
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

    def check_header(self, dcm_path) -> CheckResult:
        """
        :returns: (True|Fales, {'have': xxx, 'expect': yyy}, hdr)
        """

        hdr = self.reader.read_dicom_tags(dcm_path)
        template = self.db.get_template(hdr["Project"], hdr["SequenceName"])
        template = dict(template)

        # no template, no errors
        if template:
            errors = find_errors(template, hdr)
        else:
            errors = {}

        return {
            "conforms": not errors ,
            "errors": errors,
            "input": hdr,
            "template": dict(template),
        }
