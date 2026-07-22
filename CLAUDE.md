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
- ⚠️ **Adding a field to `Business`/`Branch`/`Product` in `domain/models.py`**: these models get converted to their GraphQL types (`BusinessType`, `BranchType`, `ProductType`, `ScoredProductType`, `ScoredBranchType`, `NearbyBranchType`, ...) by dumping the *entire* model via `to_strawberry_dict()` and unpacking it as `SomeType(**data)`. A new field not declared on the target GraphQL type breaks every query using that type with "unexpected keyword argument" at request time — `py_compile`/syntax checks won't catch it, and this already happened twice (see the warning comments in `domain/models.py` above `Business`/`Branch`/`Product`, and in `utils/serialization.py`'s `to_strawberry_dict`). Before adding a field to these 3 models: `grep -rn "BusinessType(\|BranchType(\|ProductType("` across `schema/` to find every construction site, then either add the field to the corresponding GraphQL type(s) or exclude it (for Branch, via `branch_to_dict()`'s `exclude` set in `schema/branches/utils.py`, which covers `BranchType`/`ScoredBranchType`/`NearbyBranchType` in one place).

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
