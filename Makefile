PYTHON ?= python3

.PHONY: test run build-docker

test:
	PYTHONPYCACHEPREFIX=/private/tmp/pycache $(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) -m knowledge_base_api.main

build-docker:
	docker build -t knowledge-base-api:latest .
