.PHONY: help install sync test verify clean dev-services frontend backend

help:
	@echo "Legal Immigration RAG System - Available Commands:"
	@echo ""
	@echo "  make install        - Install dependencies with uv"
	@echo "  make sync           - Sync dependencies from lock file"
	@echo "  make test           - Run all tests"
	@echo "  make verify         - Verify project setup"
	@echo "  make dev-services   - Start Redis and Weaviate with Docker"
	@echo "  make frontend       - Start frontend dev server"
	@echo "  make backend        - Start backend API server"
	@echo "  make clean          - Clean build artifacts"
	@echo ""

install:
	uv sync

sync:
	uv sync --frozen

test:
	uv run pytest

verify:
	uv run python scripts/verify_setup.py

dev-services:
	docker-compose up -d
	@echo "✓ Redis running on localhost:6379"
	@echo "✓ Weaviate running on localhost:8080"

frontend:
	cd frontend && npm run dev

backend:
	uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".hypothesis" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .coverage htmlcov/
	@echo "✓ Cleaned build artifacts"
