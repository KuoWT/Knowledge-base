PYTHON ?= python3

.PHONY: test run build-docker

test:
	PYTHONPYCACHEPREFIX=/private/tmp/pycache $(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) -m hermes.main

build-docker:
	docker build -t hermes-kb:latest .
