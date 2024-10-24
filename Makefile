.PHONY: test

# how to get into the python virtual environment
source_venv := . .venv/bin/activate 

docs/: .venv/ $(wildcard *.py) sphinx/conf.py $(wildcard sphinx/*.rst)
	$(source_venv) && sphinx-build sphinx/ docs/

test:
	$(source_venv) && python3 -m doctest change_header.py

.venv/:
	python -m venv .venv && $(source_venv) && pip install -r requirements.txt


db.sqlite:
	sqlite3 < schema.sql

# TODO: replace me actual code
db.txt:
	./00_build_db.bash
