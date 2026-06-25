PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help site serve test clean

help:
	@echo "World Cup predictor — make targets:"
	@echo "  make site   build output/index.html (runs score then site)"
	@echo "  make serve  serve output/ at http://localhost:8000 (run 'make site' first)"
	@echo "  make test   run the unit test suite"
	@echo "  make clean  remove generated output/ and data/scores.json"

site:
	$(PYTHON) -m src.score
	$(PYTHON) -m src.site

serve:
	cd output && $(PYTHON) -m http.server 8000

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

clean:
	rm -rf output
	rm -f data/scores.json
