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

## Speed
```
exdcm=Resting-state_ME_476x504.14/MR.1.3.12.2.1107.5.2.43.167046.202208231445351851262117

hyperfine "./dcmmeta2tsv.py $exdcm" "./dcmmeta2tsv.bash $exdcm" 

Benchmark 1: ./dcmmeta2tsv.py Resting-state_ME_476x504.14/MR.1.3.12.2.1107.5.2.43.167046.202208231445351851262117
  Time (mean ± σ):     952.2 ms ±  37.4 ms    [User: 559.1 ms, System: 86.9 ms]
  Range (min … max):   876.5 ms … 1014.5 ms    10 runs
 
Benchmark 2: ./dcmmeta2tsv.bash Resting-state_ME_476x504.14/MR.1.3.12.2.1107.5.2.43.167046.202208231445351851262117
  Time (mean ± σ):     822.5 ms ±  69.3 ms    [User: 73.3 ms, System: 51.0 ms]
  Range (min … max):   703.1 ms … 896.1 ms    10 runs
 
Summary
  ./dcmmeta2tsv.bash Resting-state_ME_476x504.14/MR.1.3.12.2.1107.5.2.43.167046.202208231445351851262117 ran
    1.16 ± 0.11 times faster than ./dcmmeta2tsv.py Resting-state_ME_476x504.14/MR.1.3.12.2.1107.5.2.43.167046.202208231445351851262117
```