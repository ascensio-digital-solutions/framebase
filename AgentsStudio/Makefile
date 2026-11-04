.PHONY: run web api deploy lint clean

AGENT ?= image_generator

run:
	adk run src/agents/$(AGENT)

web:
	adk web src/agents

api:
	adk api_server src/agents

deploy:
	adk deploy cloud_run src/agents/$(AGENT)

lint:
	ruff check src/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true