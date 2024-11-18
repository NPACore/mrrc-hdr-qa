from template_checker import TemplateChecker, CheckResult
from jinja2 import Template


# Define the template for Jinja
html_template = """
<html>
<head>
    <style>
        table {
            border-collapse: collapse;
            width: 100%;
        }
        th, td {
            border: 1px solid black;
            padding: 8px;
            text-align: center;
        }
        th {
            background-color: #f2f2f2;
        }
        .match { background-color: #d4edda; } /* green for matches */
        .mismatch { background-color: #f8d7da; } /* red for mismatches */
    </style>
</head>
<body>
    <h2>DICOM Header Compliance Report</h2>
    <table>
        <tr>
            <th>Header</th>
            <th>Expected Value</th>
            <th>Actual Value</th>
        </tr>
        {% for row in rows %}
            <tr class="{{ row.class_name }}">
            <td>{{ row.header }}</td>
            <td>{{ row.expected_value }}</td>
            <td>{{ row.actual_value }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

def generate_html_report(check_result: CheckResult) -> str:
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
        rows.append({
            "header": header, 
            "expected_value": expected_value,
            "actual_value": actual_value,
            "class_name": class_name
        })

    # Render the template with the data
    template = Template(html_template)
    html = template.render(rows=rows)

    return html


