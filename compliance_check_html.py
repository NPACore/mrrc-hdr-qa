from jinja2 import Template

from template_checker import CheckResult


def load_template(template_path: str) -> Template:
    """
    Load an HTML template from the template.html file

    :param template_path: Path to the HTML template file.
    :returns: A Jinja2 Template object.
    """
    with open(template_path, "r") as file:
        template_content = file.read()
    return Template(template_content)


def generate_html_report(check_result: CheckResult, template_path: str) -> str:
    """
    Generate an HTML report of DICOM header comparison, highlighting mismatches.

    :param check_result: Output from the check_header function, containing the comparison results.
    :returns: HTML string with results formatted using a Jinja2 template.
    """

    # Headers to check
    headers_to_check = ["Project", "SequenceName", "TR", "TE", "FA", "iPAT", "Comments"]

    # Initialize the rows list
    rows = []

    # Add rows for each header parameter
    for header in headers_to_check:
        expected_value = check_result["template"].get(header, "N/A")
        actual_value = check_result["input"].get(header, "N/A")
        class_name = "mismatch" if header in check_result["errors"] else "match"
        rows.append(
            {
                "header": header,
                "expected_value": expected_value,
                "actual_value": actual_value,
                "class_name": class_name,
            }
        )

    # Load the template from the file
    template = load_template(template_path)

    # Render the template with the data
    html = template.render(rows=rows)

    return html
