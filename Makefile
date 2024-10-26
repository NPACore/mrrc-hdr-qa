.PHONY: default test docs pre-commit venv-dev venv-program

default: docs

pre-commit: venv-program venv-dev .test .lint

db.sqlite:
	sqlite3 $@ < schema.sql

# how to get into the python virtual environment
source_venv := . .venv/bin/activate

## documentation. github action pushes this to 'gh-pages' branch
docs: docs/
docs/: venv-dev $(wildcard *.py) sphinx/conf.py $(wildcard sphinx/*.rst) docs/taglist.csv
	$(source_venv) && sphinx-build sphinx/ docs/
# sphinx can read in csv but not tsv, so convert for it
docs/taglist.csv: taglist.txt
	mkdir -p docs
	sed '/^#/d;s/,//g;s/\t/,/g' $< > $@

##

.lint: $(wildcard *.py) $(wildcard sphinx/*.rst) | venv-dev
	$(source_venv) && black . > .lint && isort . >> .lint && codespell -w >> .lint

test: .test
.test: change_header.py acq2sqlite.py dcmmeta2tsv.py | venv-program venv-dev  #$(wildcard *py)
	# LOGLEVEL=CRITICAL
	$(source_venv) && python3 -m doctest $^ 2>&1 | tee $@

## managing the environment
# dev requirements separate to hopefully run github actions a bit faster
.venv/:
	python3 -m venv .venv
venv-dev: .venv/bin/black
.venv/bin/black: .venv/
	$(source_venv) && pip install -r requirements_dev.txt
venv-program: .venv/bin/pydicom
.venv/bin/pydicom: .venv/
	$(source_venv) && pip install -r requirements.txt
