.PHONY: help install install-dev install-test install-prod clean lint format type-check test test-cov test-complete test-mexc test-backend run run-dev start-system setup migrate migrate-create migrate-upgrade migrate-downgrade docker-build docker-run

# Default target
help:
	@echo "COM Backend Development Commands"
	@echo "================================"
	@echo ""
	@echo "Installation:"
	@echo "  install          Install production dependencies"
	@echo "  install-dev      Install development dependencies"
	@echo "  install-test     Install test dependencies"
	@echo "  install-prod     Install production dependencies"
	@echo ""
	@echo "Development:"
	@echo "  run              Run the server"
	@echo "  run-dev          Run the server with auto-reload"
@echo "  start-system     Start complete COM system with health checks"
@echo "  setup            Run environment setup and validation"
@echo "  lint             Run linting checks"
	@echo "  format           Format code with black"
	@echo "  type-check      Run type checking with mypy"
	@echo ""
	@echo "Testing:"
	@echo "  test             Run tests"
	@echo "  test-cov         Run tests with coverage"
@echo "  test-complete    Run complete system test suite"
@echo "  test-mexc        Test MEXC integration"
@echo "  test-mexc-local  Test MEXC local package integration"
@echo "  test-backend     Test core backend functionality"
@echo ""
@echo "Database:"
	@echo "  migrate          Run database migrations"
	@echo "  migrate-create   Create new migration"
	@echo "  migrate-upgrade  Upgrade database"
	@echo "  migrate-downgrade Downgrade database"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build     Build Docker image"
	@echo "  docker-run       Run Docker container"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean            Clean up generated files"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-test:
	pip install -e ".[test]"

install-prod:
	pip install -e ".[prod]"

# Development
run:
	python start_com.py

run-dev:
	ENVIRONMENT=development DEBUG=true python start_com.py

# Code quality
lint:
	ruff check com/
	black --check com/

format:
	black com/
	ruff check --fix com/

type-check:
	mypy com/

# Testing
test:
	pytest

test-cov:
	pytest --cov=com --cov-report=html --cov-report=term-missing

# Database migrations
migrate:
	alembic upgrade head

migrate-create:
	@read -p "Enter migration message: " message; \
	alembic revision --autogenerate -m "$$message"

migrate-upgrade:
	alembic upgrade head

migrate-downgrade:
	alembic downgrade -1

# Docker
docker-build:
	docker build -t com-backend .

docker-run:
	docker run -p 8000:8000 --env-file .env com-backend

# Maintenance
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	find . -type f -name "coverage.xml" -delete

# Pre-commit hooks
install-hooks:
	pre-commit install

run-hooks:
	pre-commit run --all-files

# New testing commands
test-complete:
	python test_com_complete.py

test-mexc:
	python test_mexc_symbol_specific.py

test-mexc-local:
	python test_mexc_local_integration.py

test-backend:
	python test_com_backend.py

# System management
start-system:
	python start_com_system.py

setup:
	python setup_environment.py
