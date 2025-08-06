# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Key Development Commands

### Testing
- Run all tests: `uv run pytest`
- Run specific test: `uv run pytest test/test_models.py::TestClassName::test_method_name`
- Run tests with coverage: `uv run pytest --cov=django_mongodb`
- Run tests for different Django versions: `tox` or `tox -e django52`

### Code Quality
- Format and lint: `ruff check . --fix`
- Type checking: If you implement type checking, run mypy to validate

### Local MongoDB Setup
- Setup local MongoDB: `make setup_local_db`
- Start local MongoDB: `make start_local_db`
- Default MongoDB runs on port 3307 (configured via Atlas CLI)

## Architecture Overview

This is a Django database backend for MongoDB, implementing Django's database backend API to allow Django models to work with MongoDB collections.

### Core Components

1. **django_mongodb/base.py**: Main DatabaseWrapper that integrates with Django's database layer
   - Connects to MongoDB using pymongo
   - Maps Django field types to MongoDB types
   - Manages database connections

2. **django_mongodb/models.py**: Custom field types
   - `ObjectIdAutoField`: Primary key field using MongoDB ObjectIds
   - `ObjectIdField`: Regular ObjectId field
   - `DecimalField`: Compatibility layer for Django < 5.2

3. **django_mongodb/compiler.py**: SQL-to-MongoDB query translation
   - Converts Django ORM queries to MongoDB queries
   - Handles filters, aggregations, and joins

4. **django_mongodb/query.py**: Extended query features
   - `RawMongoDBQuery`: Direct MongoDB query support
   - `prefer_search()`: MongoDB $search operator integration

### Key Design Patterns

- **Single Table Inheritance**: Multiple models can share the same MongoDB collection using `db_table` and `parent_link`
- **No Migrations**: MongoDB is schema-less, so migrations are disabled via DatabaseRouter
- **ObjectId Primary Keys**: Models use `ObjectIdAutoField` by default (set in AppConfig)

### Testing Approach

- Uses pytest with Django plugin
- Test database configured in `testproject/settings.py`
- Requires MongoDB instance (local or remote via MONGODB_URL env var)
- Tests cover models, queries, fields, and database operations

### Important Notes

- Not supported as primary database (Django admin/auth require integer PKs)
- Requires DatabaseRouter to route models to MongoDB
- Collections use app_label + model_name convention (e.g., `myapp_mymodel`)
- DecimalField handling differs between Django versions (5.2+ vs earlier)
