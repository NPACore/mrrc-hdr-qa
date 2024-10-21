# MRRC Dicom Header Quality Assurance
Parse dicoms into a template database and alert on non-conforming sequences.

See
  * `make docs/` for building sphinx documentation 
   * locally in [`sphinx/index.rst`](sphinx/index.rst))
   * reference for  restructured text [`sphinx docstrings`](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
  * `make test` for using `doctests`
  * [`schema.sql`](schema.sql) for DB schema

## Strategy 

 * build sqlite db of all acquisitions with subset of parameters
 * use db summary to pull out "ideal template"
 * check new sessions' acquisitions against template to alert

## Prior Art
 * mrQA
 * sister project https://github.com/NPACore/mrqart/
