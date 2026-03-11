# MRQART Changes — 2026-03-11

## Features

### Physicist lookup in email project headers
**File:** `mrqart/email_latest_flip.py`

Added `get_physicist_for_project(sql, project)` which looks up the assigned physicist
from the `project` table (added via `db-project` merge) by matching the suffix after
`^` in the acq_param Project name against the project table's `Project` column,
case-insensitively.

```sql
SELECT Physicist
FROM project
WHERE UPPER(Project) = UPPER(SUBSTR(?, INSTR(?, '^') + 1))
```

In `main()`, a `physicist_by_project` dict is pre-computed after `evaluate_rows` and
passed into `build_email` as a new parameter. This keeps `build_email` as a pure
rendering function with no DB access.

Project headers in the email now show the physicist when one is assigned:
```
Brain^STUDY-001 (5 nonconforming sequences; 2 sessions today; physicist: Johnson):
```

Projects without a match in the project table show no physicist string.

---

## Notes on project table matching

The `project` table (populated by `01b_xsl2db.R`) uses short project names like
`STUDY-001`, while `acq_param.Project` uses full names like `Brain^STUDY-001`.
The suffix-after-`^` match covers most cases. Projects without a `^` (e.g. `STUDY-002`)
are matched directly since `INSTR` returns 0 when `^` is not found,
and `SUBSTR(x, 1)` returns the full string.

Some projects in `acq_param` do not yet have entries in the project table —
physicist will show as blank for these until the project table is populated.


# MRQART Changes — 2026-03-11 (multiecho merge)

## Merges

### `multiecho` → `cli`
Clean merge. Adds multiecho support to the DB update pipeline.
Two bugs were fixed immediately after merging (see below).

---

## New Features

### `read_many_dicom_tags` in `DicomTagReader`
**File:** `mrqart/dcmmeta2tsv.py`

New method on `DicomTagReader` that reads tags from multiple dicoms from the same
acquisition and combines TE values when they differ across dicoms (multiecho case).
Multiple TEs are stored as a comma-separated string e.g. `"4.8,7.4,10.0"`.

```python
def read_many_dicom_tags(self, dcm_paths: list[os.PathLike]) -> TagValues:
```

Called by `update_mrrc_db` in place of `read_dicom_tags` so the DB now stores
combined TE for multiecho acquisitions.

### `find_first_dicoms` now returns multiple dicoms per acquisition
**File:** `mrrc_dbupdate.py`

Previously returned `list[PathLike]` (one dicom per acquisition). Now returns
`list[list[PathLike]]` — a list of dicoms per acquisition, sorted by filename,
so `read_many_dicom_tags` can walk through them to detect TE changes.

The `find` command was also updated to use `print0 | sort -zn` instead of
`-print -quit` so dicoms are returned in a consistent order rather than
filesystem order.

### Import cleanup in `mrrc_dbupdate.py`
**File:** `mrrc_dbupdate.py`

Updated imports from bare module imports to package-relative:
```python
# before
import acq2sqlite
import dcmmeta2tsv

# after
from mrqart.acq2sqlite import DBQuery
from mrqart.dcmmeta2tsv import DicomTagReader
```

---

## Bug Fixes

### `read_many_dicom_tags`: `IndexError` on list append
**File:** `mrqart/dcmmeta2tsv.py`

`all_tags` was initialized as an empty list `[]` but the loop used
`all_tags[i] = ...` (index assignment), which raises `IndexError` on the
first iteration. Fixed to use `all_tags.append(...)` and updated the
first-iteration reference from `all_tags[i]` to `all_tags[0]`.

### `mrrc_dbupdate.py`: syntax error and invalid escape sequences
**File:** `mrrc_dbupdate.py`

The `findcmd` f-string had an unmatched `)` and unescaped backslashes
causing a `SyntaxError` and `SyntaxWarning`. Fixed:
```python
# before (broken)
findcmd = f"find '{seqdir}' -maxdepth 1 -type f \( ... \) -print0 | sort -zn") 

# after
findcmd = f"find '{seqdir}' -maxdepth 1 -type f \\( ... \\) -print0 | sort -zn"
```
# MRQART Changes — 2026-03-11 (multiecho TE support)

## Features

### Multiecho TE handling in `TemplateChecker`
**File:** `mrqart/template_checker.py`

Added a specific TE comparison case in `find_errors` to handle multiecho acquisitions
where the current header may contain comma-separated TE values (e.g. `"4.8,7.4,10.0"`).
A sequence is considered conforming if the template TE matches any of the values in
the comma-separated list.

```python
elif k == "TE":
    # multiecho: current header may have comma-separated TEs e.g. "4.8,7.4"
    # pass if template TE matches any of the values in the list
    t_norm = _norm_str(t_k)
    h_values = [_norm_str(v.strip()) for v in str(h_k).split(",")]
    check = t_norm in h_values
```

Behavior:
- Single TE `"38.76"` vs template `"38.76"` → pass (existing behavior preserved)
- Multiecho `"4.8,38.76"` vs template `"38.76"` → pass
- Multiecho `"4.8,7.4"` vs template `"38.76"` → fail (template TE not present)
- Wrong single TE `"14.6"` vs template `"38.76"` → fail (existing behavior preserved)

---

## Tests

### New tests in `tests/test_template.py`

Four new tests covering the TE comparison cases:

- `test_find_errors_te_single` — single TE matches template exactly
- `test_find_errors_te_multiecho_match` — template TE is one of the multiecho values
- `test_find_errors_te_multiecho_no_match` — template TE is not in the multiecho list
- `test_find_errors_te_wrong` — wrong single TE still fails

### Fixed tests in `tests/test_email_latest_flip.py`

Two `build_email` tests were failing because `physicist_by_project` is now a required
parameter. Added `physicist_by_project={}` to both calls:
- `test_build_email_structure_and_subject_flags`
- `test_build_email_green_when_no_nonconforming_and_no_mia`

### Fixed test in `tests/test_seq_report.py`

`test_seq_report_te_mismatch_sorted_values` was asserting `"saw 5, 12"` but the correct
behavior is `"saw 12"` — `_summarize_mismatches` correctly excludes values that match
the expected value from the `values_seen` list. Updated assertion to match correct behavior.

