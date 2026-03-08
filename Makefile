.PHONY: install lint test run-api run-worker panos-fixtures

install:
	pip install -r requirements-dev.txt

lint:
	ruff check .
	ruff format --check .

lint-fix:
	ruff check --fix .
	ruff format .

test:
	pytest -v --tb=short

test-cov:
	pytest -v --cov --cov-report=term-missing

run-api:
	uvicorn am_i_blocked_api:app --reload --host 0.0.0.0 --port 8000

run-worker:
	python -m am_i_blocked_worker.main

migrate:
	alembic upgrade head

docker-up:
	docker compose -f infra/docker-compose.yml up --build

docker-down:
	docker compose -f infra/docker-compose.yml down

panos-fixtures:
	# run the helper using environment variables or explicit args
	@bash scripts/gather_panos_fixtures.sh "$${PANOS_HOST}" "$${PANOS_KEY}" "$${PANOS_XPATH}"
