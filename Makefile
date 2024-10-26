.PHONY: test docs pre-commit

# how to get into the python virtual environment
source_venv := . .venv/bin/activate 

docs: docs/
docs/: .venv/ $(wildcard *.py) sphinx/conf.py $(wildcard sphinx/*.rst) docs/taglist.csv
	$(source_venv) && sphinx-build sphinx/ docs/

docs/taglist.csv: taglist.txt
	mkdir -p docs
	sed '/^#/d;s/,//g;s/\t/,/g' $< > $@

test: .test
.test: change_header.py acq2sqlite.py #$(wildcard *py)
	# LOGLEVEL=CRITICAL
	$(source_venv) && python3 -m doctest $^ |& tee $@

.venv/:
	python3 -m venv .venv && $(source_venv) && \
		pip install -r requirements.txt && \
		pip install -r requirements_dev.txt


db.sqlite:
	sqlite3 $@ < schema.sql

# TODO: replace me actual code
db.txt:
	./00_build_db.bash

pre-commit: .venv/ .test
	$(source_venv) && black . && isort . && codespell -w
