from template_checker import TemplateChecker, CheckResult

def generate_html_report(check_result: CheckResult) -> str:
    """
    Generate an HTML report of DICOM header comparison, highlighting mismatches.

    :param check_result: Output from the check_header function, containing the comparison results.
    :returns: HTML string with results formatted in a table.
    """

    # HTML Table Start
    headers_to_check = ["Project", "SequenceName", "TR", "TE", "FA", "iPAT", "Comments"]
    html = """
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
    """

    # Add rows for each header parameter
    for header in headers_to_check:
        expected_value = check_result["template"].get(header, "N/A")
        actual_value = check_result["input"].get(header, "N/A")
        class_name = "mismatch" if header in check_result["errors"] else "match"

        # Add the row to HTML table
        html += f"""
            <tr class="{class_name}">
                <td>{header}</td>
                <td>{expected_value}</td>
                <td>{actual_value}</td>
            </tr>
        """

    # Close the HTML structure
    html += """
        </table>
    </body>
    </html>
    """

    return html

                
