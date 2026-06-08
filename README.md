# Mealio

[![Backend Tests](https://github.com/Pavel404-dev/Mealio/actions/workflows/backend-tests.yml/badge.svg)](https://github.com/Pavel404-dev/Mealio/actions/workflows/backend-tests.yml)

Mealio is an AI-powered mobile application designed to generate recipes and nutrition information from ingredients that users already have available.

The project is being developed as part of a Bachelor's Thesis and currently uses a monorepo containing the FastAPI backend, the planned Flutter mobile client, and technical documentation.

## Overview

Mealio aims to help users:

* manage ingredients available at home;
* generate recipes from available ingredients;
* organize recipes and meal plans;
* calculate meal and daily nutrition summaries;
* classify recipes by dietary preferences;
* receive AI-assisted recipe and nutrition recommendations.

The project is currently under active development.

## Project Status

### Implemented

The backend currently includes:

* user profile creation;
* user profile retrieval by ID;
* partial user profile updates;
* ingredient management;
* user pantry management;
* recipe management;
* meal plan management;
* meal plan item management;
* meal plan nutrition summaries;
* daily nutrition summaries;
* Argon2 password hashing and verification utilities;
* PostgreSQL persistence;
* asynchronous SQLAlchemy integration;
* Alembic migrations;
* automated pytest test coverage;
* GitHub Actions backend CI.

### Planned

The following functionality is planned for future development:

* user registration with passwords;
* login and logout;
* JWT access tokens;
* refresh tokens;
* authenticated and protected routes;
* current-user endpoints;
* password reset;
* email verification;
* AI recipe generation;
* AI recipe classification;
* personalized nutrition recommendations;
* Flutter mobile application integration;
* production deployment.

## Architecture

```mermaid
flowchart LR
    Mobile["Flutter Mobile App<br/>planned / under development"]
    API["FastAPI REST API"]
    Services["Service Layer"]
    Repositories["Repository Layer"]
    Database[("PostgreSQL 17")]
    AI["AI Recipe Generation Service<br/>planned"]

    Mobile -->|"HTTPS / JSON"| API
    API --> Services
    Services --> Repositories
    Repositories --> Database
    Services -.->|"future integration"| AI
```

The backend follows a layered architecture:

```text
API endpoints
    ↓
Service layer
    ↓
Repository layer
    ↓
SQLAlchemy models
    ↓
PostgreSQL
```

This separation keeps HTTP handling, business logic, persistence logic, and database models isolated from each other.

## Technology Stack

### Mobile

* Flutter
* Dart

### Backend

* Python 3.12
* FastAPI
* Uvicorn
* Pydantic
* pwdlib with Argon2

### Database

* PostgreSQL 17
* Async SQLAlchemy
* asyncpg
* Alembic

### Testing

* pytest
* pytest-asyncio
* HTTPX

### Development and CI

* Git
* GitHub Issues
* GitHub Pull Requests
* GitHub Actions
* Docker Compose
* Husky

## Repository Structure

```text
Mealio/
├── .github/
│   └── workflows/
│       └── backend-tests.yml
│
├── .husky/
│   └── pre-commit
│
├── backend/
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   ├── .env.example
│   ├── alembic.ini
│   ├── README.md
│   └── requirements.txt
│
├── mobile/
│   └── Flutter mobile application
│
├── docs/
│   └── Architecture, database, UML, and thesis documentation
│
├── docker-compose.yml
├── pytest.ini
├── README.md
└── .gitignore
```

Mealio is intentionally maintained as a monorepo because the backend, mobile application, and project documentation belong to the same product and Bachelor's Thesis.

## Prerequisites

Before running the backend locally, install:

* Git
* Python 3.12
* Docker Desktop with Docker Compose
* PostgreSQL client tools, optional
* Flutter SDK, required only for mobile development

Verify the required tools:

```bash
git --version
python --version
docker --version
docker compose version
```

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Pavel404-dev/Mealio.git
cd Mealio
```

### 2. Create a Python virtual environment

From the repository root:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Verify the active interpreter:

```bash
python --version
python -c "import sys; print(sys.executable)"
```

### 3. Install backend dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

### 4. Create the backend environment file

Windows PowerShell:

```powershell
Copy-Item backend\.env.example backend\.env
```

macOS or Linux:

```bash
cp backend/.env.example backend/.env
```

The default local database URL is:

```text
postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio
```

The `.env` file is local configuration and must not be committed.

### 5. Start PostgreSQL

From the repository root:

```bash
docker compose up -d postgres
```

Check the service:

```bash
docker compose ps
```

View PostgreSQL logs:

```bash
docker compose logs postgres
```

Stop the local services:

```bash
docker compose down
```

To stop the services and remove the PostgreSQL volume:

```bash
docker compose down -v
```

> Removing the volume permanently deletes the local database data.

### 6. Apply database migrations

Move into the backend directory:

```bash
cd backend
```

Apply all migrations:

```bash
alembic upgrade head
```

Check the current migration:

```bash
alembic current
```

Check whether the ORM models require a new migration:

```bash
alembic check
```

Return to the repository root when needed:

```bash
cd ..
```

### 7. Run the FastAPI backend

From the `backend` directory:

```bash
python -m uvicorn app.main:app --reload
```

The backend is available at:

```text
http://127.0.0.1:8000
```

## API Documentation

When the backend is running, open:

| Resource       | URL                                  |
| -------------- | ------------------------------------ |
| Health check   | `http://127.0.0.1:8000/health`       |
| Swagger UI     | `http://127.0.0.1:8000/docs`         |
| ReDoc          | `http://127.0.0.1:8000/redoc`        |
| OpenAPI schema | `http://127.0.0.1:8000/openapi.json` |

Expected health response:

```json
{
  "status": "ok",
  "service": "mealio-backend"
}
```

## API Modules

The backend currently provides functionality for:

| Module              | Current capabilities                                   |
| ------------------- | ------------------------------------------------------ |
| Users               | Create, retrieve, and partially update user profiles   |
| Ingredients         | Create, list, retrieve, update, and delete ingredients |
| Pantry              | Manage ingredients stored by a user                    |
| Recipes             | Create, list, retrieve, update, and delete recipes     |
| Meal plans          | Manage meal plans and meal plan items                  |
| Nutrition summaries | Calculate meal plan and daily nutrition totals         |
| Security utilities  | Hash and verify passwords using Argon2                 |

Authentication endpoints are not implemented yet.

## Running Tests

### Important database warning

Backend tests require a dedicated disposable PostgreSQL database.

Never set `TEST_DATABASE_URL` to:

* a production database;
* a database containing important data;
* the regular local `mealio` development database.

The current test fixtures create and remove application tables during test execution.

### 1. Create the test database

Start PostgreSQL first:

```bash
docker compose up -d postgres
```

Create the test database once:

```bash
docker compose exec postgres createdb -U mealio_user mealio_test
```

If the database already exists, this command may report that it cannot be created again. That message can be ignored when `mealio_test` is already available.

### 2. Configure test environment variables

Windows PowerShell:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test"
$env:TEST_DATABASE_URL="postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test"
```

macOS or Linux:

```bash
export DATABASE_URL="postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test"
export TEST_DATABASE_URL="postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test"
```

### 3. Run the complete backend test suite

From the repository root:

```bash
python -m pytest -v
```

Run one test file:

```bash
python -m pytest backend/tests/test_security.py -v
```

Run one test by name:

```bash
python -m pytest backend/tests/test_security.py -v -k "unicode"
```

## Database Migrations

Create migrations only when the database schema changes.

From the `backend` directory:

```bash
alembic revision --autogenerate -m "describe schema change"
```

Review the generated migration before applying it.

Apply migrations:

```bash
alembic upgrade head
```

Check for unexpected schema differences:

```bash
alembic check
```

A dependency, documentation, service, or utility-only change normally does not require a database migration.

## Development Workflow

Mealio is developed through small, isolated GitHub issues.

The expected workflow is:

1. Create a focused GitHub issue.
2. Update the local `main` branch.
3. Create a branch using the issue number.
4. Implement only the requested scope.
5. Run the relevant tests.
6. Review `git diff`.
7. Use a Conventional Commit message.
8. Push the branch.
9. Open a pull request into `main`.
10. Wait for GitHub Actions.
11. Address review comments.
12. Squash and merge.
13. Update local `main`.
14. Delete the completed feature branch.

Example branch names:

```text
feat/32-password-hashing
docs/33-improve-readme
fix/34-example-fix
```

Example commit messages:

```text
feat(auth): add password hashing utilities
docs: improve project README and setup guide
fix(users): handle duplicate normalized emails
```

## Continuous Integration

GitHub Actions automatically:

1. starts PostgreSQL 17;
2. installs backend dependencies;
3. applies Alembic migrations;
4. runs the complete backend test suite.

The workflow runs for pull requests targeting `main` and for pushes to `main`.

## Security

The project currently includes:

* Argon2 password hashing utilities;
* random password salts;
* safe password verification;
* database-backed email uniqueness;
* environment-based database configuration;
* ignored local `.env` files.

The project does not currently include complete authentication.

Do not use the application as a production authentication system until registration, login, token handling, protected routes, and deployment security have been completed and reviewed.

## Roadmap

### Backend foundation

* [x] Initial FastAPI application
* [x] PostgreSQL integration
* [x] SQLAlchemy models
* [x] Alembic migrations
* [x] Ingredients and pantry APIs
* [x] Recipes API
* [x] Meal plans API
* [x] Nutrition summaries
* [x] Users API
* [x] Backend CI
* [x] Password hashing utilities

### Authentication

* [ ] Registration schema
* [ ] Registration endpoint
* [ ] Login endpoint
* [ ] JWT access tokens
* [ ] Refresh tokens
* [ ] Authentication dependencies
* [ ] Current-user endpoint
* [ ] Protected routes
* [ ] Password reset
* [ ] Email verification

### Artificial intelligence

* [ ] Recipe generation from available ingredients
* [ ] Recipe classification
* [ ] Nutrition recommendation logic
* [ ] AI request persistence and monitoring
* [ ] Generated recipe images

### Mobile application

* [ ] Flutter application foundation
* [ ] API client
* [ ] Authentication screens
* [ ] Pantry screens
* [ ] Recipe generation screens
* [ ] Meal planning screens
* [ ] Nutrition summary screens

### Production readiness

* [ ] Deployment configuration
* [ ] Production environment configuration
* [ ] Structured logging
* [ ] Monitoring
* [ ] Rate limiting
* [ ] Coverage reporting
* [ ] Release versioning

## Documentation

Project documentation is stored in:

```text
docs/
```

It is intended to contain:

* architecture decisions;
* database documentation;
* ER diagrams;
* UML diagrams;
* API documentation;
* Bachelor's Thesis materials.

## Academic Context

Mealio is developed as part of a Bachelor's Thesis focused on an intelligent AI-powered mobile application for instant recipe and nutrition generation based on available ingredients.

The project demonstrates:

* mobile application development;
* REST API design;
* asynchronous database access;
* relational database modeling;
* automated testing;
* continuous integration;
* authentication and application security;
* future AI service integration.

## Author

**Pavel Potapenko**

GitHub: [Pavel404-dev](https://github.com/Pavel404-dev)
