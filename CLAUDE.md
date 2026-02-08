# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

**Llego Backend** is a FastAPI app with GraphQL (Strawberry) + REST endpoints.
The project follows a layered structure:

- `api/` and `schema/` for interfaces
- `services/` for business logic
- `repositories/` for data access
- `domain/` for Pydantic domain models
- `clients/` for infrastructure clients (MongoDB, Qdrant, Gemini, S3)

## Project Structure

```text
LlegoBackend/
├── main.py
├── api/
├── schema/
├── services/
│   ├── orders_service.py
│   ├── payments_service.py
│   └── payments/
├── repositories/
│   ├── orders_repository.py
│   ├── payments_attempt_repository.py
│   ├── platform_repository.py
│   └── __init__.py
├── domain/
│   ├── models.py
│   ├── orders.py
│   ├── payments.py
│   ├── business_types.py
│   ├── error_logs.py
│   └── platform.py
├── clients/
├── scripts/
│   ├── export_schema.py
│   ├── seed_business_types.py
│   ├── seed_delivery_zones.py
│   ├── seed_product_categories.py
│   └── *.py migrations/utilities
├── data/
└── docs/
```

## Development Commands

### Run API

```bash
python main.py
```

or

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Environment Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Export GraphQL Schema

```bash
python scripts/export_schema.py
```

### Seed Data

```bash
python scripts/seed_business_types.py
python scripts/seed_delivery_zones.py
python scripts/seed_product_categories.py
```

## Architectural Conventions

- Keep all domain entities in `domain/` (no model files in repo root).
- Keep business logic in `services/`.
- Keep persistence logic in `repositories/`.
- Keep external providers/SDK wiring in `clients/`.
- Keep one-off scripts, seeds, and migration utilities in `scripts/`.
- Import repositories via `repositories/__init__.py` exported instances when possible.

## Notes

- MongoDB collection `bussisnes` is intentionally misspelled and must be kept as-is for compatibility.
- GraphQL entrypoint is `/graphql`; schema download endpoints are mounted in `main.py`.

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
