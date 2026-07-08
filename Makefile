SHELL := /usr/bin/env bash

.PHONY: help dev up down logs api-test web-test lint typecheck format

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-16s %s\n", $$1, $$2}'

dev: up ## Start the local development stack

up: ## Start Docker Compose services
	docker compose up --build

down: ## Stop Docker Compose services
	docker compose down

logs: ## Tail Docker Compose logs
	docker compose logs -f

api-test: ## Run backend tests
	cd apps/api && pytest

web-test: ## Run frontend tests
	cd apps/web && npm test -- --run

lint: ## Run backend and frontend lint checks
	cd apps/api && ruff check src tests
	cd apps/web && npm run lint

typecheck: ## Run backend type checks
	cd apps/api && mypy src

format: ## Format backend and frontend code
	cd apps/api && ruff format src tests
	cd apps/web && npm run format
