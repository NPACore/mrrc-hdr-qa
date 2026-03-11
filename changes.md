# MRQART Changes — 2026-03-1

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

