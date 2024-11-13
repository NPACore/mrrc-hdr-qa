# test compliance_check_html.py
import pytest
from compliance_check_html import generate_html_report, TemplateChecker, CheckResult

@pytest.fixture
def example_check_result():
    """Fixture to create an example CheckResult for testing"""
    return {
            "conforms": False,
            "errors": {
                "TR": {"expect": "1300", "have": "1400"},
                "FA": {"expect": "60", "have": "70"},
            },
            "input": {
                "Project": "Brain^wpc-8620",
                "SequenceName": "HabitTask",
                "TR": "1400",
                "TE": "30",
                "FA": "70",
                "iPAT": "GRAPPA",
                "Comments": "Unaliased MB3/PE4/LB SENS1",
            },
            "template": {
                "Project": "Brain^wpc-8620",
                "SequenceName": "HabitTask",
                "TR": "1300",
                "TE": "30",
                "FA": "60",
                "iPAT": "GRAPPA",
                "Comments": "Unaliased MB3/PE4/LB SENSE1",
            },
    }

def test_generate_html_report(example_check_result):
    """Test if HTML report generation works as expected"""
    html_report = generate_html_report(example_check_result)

    # Save the HTML report to a file
    with open("generated_report.html", "w") as f:
        f.write(html_report)

    # Show that the file has been generated
    print("Generated HTML report saved as 'generated_report.html'")

    # Cehck that table headers and rows contain expected values
    assert "Project" in html_report
    assert "HabitTask" in html_report
    assert "TR" in html_report
    assert "1400" in html_report # The 'have' value in input
    assert "1300" in html_report # The 'expect' value in template

    # Check color coding: errors should have red background, matches green
    assert 'class="mismatch"' in html_report # For mismatches
    assert 'class="match"' in html_report # For matches

    # Check overall structure includes both "Expected" and "Actual" columns
    assert "<th>Expected Value</th>" in html_report
    assert "<th>Actual Value</th>" in html_report

if __name__ == "__main__":
    pytest.main(["-v", "test_generate_dicom_report.py"])
