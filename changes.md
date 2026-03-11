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

