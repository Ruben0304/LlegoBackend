# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

**Llego Backend** is a FastAPI application providing both GraphQL and REST APIs for a local business/branch/product discovery platform. The architecture follows a repository pattern with async MongoDB operations.

### Core Components

- **FastAPI + Strawberry GraphQL**: Dual API interface (REST and GraphQL) with GraphiQL playground at `/graphql`
- **MongoDB with Motor**: Async MongoDB driver for all data operations
- **Repository Pattern**: Domain-specific repositories (`UserRepository`, `BusinessRepository`, `BranchRepository`, `ProductRepository`) handle all database queries
- **Pydantic Models**: Data validation and serialization using Pydantic v2

### Data Model Relationships

- `User` → owns → `Business` (via `ownerId`)
- `Business` → has many → `Branch` (via `businessId`)
- `Branch` → has many → `Product` (via `branchId`)
- `Branch` → managed by → `User[]` (via `managerIds`)

Note: MongoDB collection `bussisnes` is misspelled in the database (not `businesses`).

### Project Structure

```
LlegoBackend/
├── main.py                        # FastAPI app initialization, middleware, and main endpoints
├── database.py                    # MongoDB connection management with lifespan
├── models.py                      # Pydantic models for data validation
├── export_schema.py               # Utility to export GraphQL schema
├── repositories/                  # Repository pattern implementations
│   ├── __init__.py                # Repository instances export
│   ├── user_repository.py         # User database operations
│   ├── business_repository.py     # Business database operations
│   ├── branch_repository.py       # Branch database operations
│   └── product_repository.py      # Product database operations
├── schema/                        # GraphQL module (organized by entity)
│   ├── __init__.py                # Exports for schema module
│   ├── schema.py                  # GraphQL schema configuration
│   ├── users/                     # User GraphQL definitions
│   │   ├── __init__.py
│   │   ├── types.py               # User GraphQL types
│   │   └── queries.py             # User GraphQL queries
│   ├── businesses/                # Business GraphQL definitions
│   │   ├── __init__.py
│   │   ├── types.py               # Business GraphQL types
│   │   └── queries.py             # Business GraphQL queries
│   ├── branches/                  # Branch GraphQL definitions
│   │   ├── __init__.py
│   │   ├── types.py               # Branch GraphQL types
│   │   └── queries.py             # Branch GraphQL queries
│   └── products/                  # Product GraphQL definitions
│       ├── __init__.py
│       ├── types.py               # Product GraphQL types
│       └── queries.py             # Product GraphQL queries
├── api/                           # REST API module
│   ├── __init__.py                # Exports for API module
│   └── routes.py                  # REST endpoint definitions
└── data/                          # JSON seed data for MongoDB collections
```

### Module Organization

- **repositories/**: Repository pattern implementations for each entity
  - Each repository handles async database operations for its entity
  - Provides methods like `get_all()`, `get_by_id()`, `search()`, and entity-specific queries
  - Repository instances are exported from `repositories/__init__.py`

- **schema/**: GraphQL-related code organized by entity
  - Each entity has its own directory with `types.py` and `queries.py`
  - `schema.py` combines all queries using multiple inheritance
  - Clean separation of concerns: types define GraphQL schema, queries define resolvers

- **api/**: REST API endpoints organized by router

- **models.py**: Pydantic models for data validation (no business logic)

- **database.py**: Database connection and lifecycle management

- **main.py**: Application entry point, minimal configuration and startup

## Development Commands

### Running the Application

```bash
# Start development server with auto-reload
python main.py

# Alternative: uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server runs at `http://localhost:8000`:
- REST API: `http://localhost:8000/`
- GraphQL Playground: `http://localhost:8000/graphql`
- GraphQL Schema SDL: `http://localhost:8000/graphql/schema`
- GraphQL Schema Download: `http://localhost:8000/graphql/schema.graphql`

### Environment Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### Schema Export

```bash
# Export GraphQL schema to schema.graphql and schema.json
python export_schema.py
```

## MongoDB Configuration

Connection details are hardcoded in `database.py`:
- URL: `mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627`
- Database: `llego`
- Collections: `users`, `bussisnes`, `branches`, `products`

The database connection uses FastAPI's lifespan context manager for proper startup/shutdown handling.

## Repository Pattern Usage

All data access goes through repository instances exported from `repositories/`:
- `users_repo.get_all()`, `users_repo.get_by_id(id)`, `users_repo.search(query)`
- `businesses_repo.get_all()`, `businesses_repo.get_by_owner(owner_id)`, `businesses_repo.search(query)`
- `branches_repo.get_all()`, `branches_repo.get_by_business(business_id)`, `branches_repo.search(query)`
- `products_repo.get_all()`, `products_repo.get_by_branch(branch_id)`, `products_repo.get_available()`, `products_repo.search(query)`

All repository methods are async and return Pydantic model instances.

## GraphQL Query Examples

The GraphQL API exposes queries for users, businesses, branches, and products with filtering and search capabilities. Access the interactive GraphiQL playground at `/graphql` for documentation and testing.

## CORS Configuration

CORS is configured to allow all origins (`allow_origins=["*"]`) for development. Update `main.py` CORS middleware for production use.

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
