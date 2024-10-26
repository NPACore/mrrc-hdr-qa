.PHONY: test doc docs

# how to get into the python virtual environment
source_venv := . .venv/bin/activate 

doc docs: docs/
docs/: .venv/ $(wildcard *.py) sphinx/conf.py $(wildcard sphinx/*.rst)
	$(source_venv) && sphinx-build sphinx/ docs/

test: .test
.test: change_header.py acq2sqlite.py #$(wildcard *py)
	$(source_venv) && python3 -m doctest $^ |& tee $@

.venv/:
	python3 -m venv .venv && $(source_venv) && pip install -r requirements.txt


db.sqlite:
	sqlite3 $@ < schema.sql

# TODO: replace me actual code
db.txt:
	./00_build_db.bash
