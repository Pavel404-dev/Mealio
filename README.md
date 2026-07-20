# Mealio

[![Backend Tests](https://github.com/Pavel404-dev/Mealio/actions/workflows/backend-tests.yml/badge.svg)](https://github.com/Pavel404-dev/Mealio/actions/workflows/backend-tests.yml)

Mealio is an AI-powered meal planning application designed to help users manage ingredients, generate recipes, organize meal plans, and calculate nutrition summaries.

The project is being developed as part of a Bachelor's Thesis and is maintained as a monorepo containing the FastAPI backend, planned Flutter mobile client, and technical documentation.

## Overview

Mealio aims to help users:

* manage ingredients available at home;
* manage a personal pantry;
* create and organize recipes;
* create meal plans;
* calculate meal plan nutrition summaries;
* calculate daily nutrition summaries;
* authenticate users with JWT access tokens;
* generate AI-assisted recipe previews from pantry and nutrition preferences.

The project is currently under active development.

## Project Status

### Implemented

The backend currently includes:

* user profile creation;
* user profile retrieval by ID;
* partial user profile updates;
* user registration;
* user login;
* JWT access token generation;
* current authenticated user endpoint;
* Argon2 password hashing and verification;
* ingredient management;
* user pantry management;
* recipe management;
* meal plan management;
* meal plan item management;
* meal plan nutrition summaries;
* daily nutrition summaries;
* PostgreSQL persistence;
* asynchronous SQLAlchemy integration;
* Alembic database migrations;
* Dockerfile for the backend;
* local Docker Compose setup for backend and PostgreSQL;
* automated backend CI with GitHub Actions;
* Ruff lint check;
* Ruff format check;
* Alembic migration checks;
* pytest test suite;
* backend test coverage report;
* backend Docker image build check;
* authenticated AI recipe generation preview with structured output.

### Planned

The following functionality is planned for future development:

* refresh tokens;
* logout flow;
* password reset;
* email verification;
* saving generated AI recipes;
* AI recipe classification;
* personalized nutrition recommendations;
* Flutter mobile application integration;
* production or staging deployment.

## Architecture

```mermaid
flowchart LR
    Mobile["Flutter Mobile App<br/>planned / under development"]
    API["FastAPI REST API"]
    Services["Service Layer"]
    Repositories["Repository Layer"]
    Database[("PostgreSQL 17")]
    AI["AI Recipe Generation Provider"]

    Mobile -->|"HTTPS / JSON"| API
    API --> Services
    Services --> Repositories
    Repositories --> Database
    Services -->|"structured recipe preview"| AI
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

### Backend

* Python 3.12
* FastAPI
* Uvicorn
* Pydantic
* Pydantic Settings
* pwdlib with Argon2
* PyJWT
* OpenAI Python SDK

### Database

* PostgreSQL 17
* Async SQLAlchemy
* asyncpg
* Alembic

### Testing and Quality

* pytest
* pytest-asyncio
* pytest-cov
* HTTPX
* Ruff

### DevOps and Tooling

* Docker
* Docker Compose
* GitHub Actions
* GitHub Issues
* GitHub Pull Requests
* Husky

### Mobile

* Flutter
* Dart

The mobile application is planned / under development.

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
│   ├── .dockerignore
│   ├── .env.example
│   ├── alembic.ini
│   ├── Dockerfile
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

Before running the project locally, install:

* Git
* Docker
* Docker Compose
* Python 3.12, required for manual backend setup
* PostgreSQL client tools, optional
* Flutter SDK, required only for mobile development

Verify the required tools:

```bash
git --version
docker --version
docker compose version
python --version
```

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Pavel404-dev/Mealio.git
cd Mealio
```

### 2. Run backend with Docker Compose

The recommended local backend startup method is Docker Compose.

From the repository root:

```bash
docker compose up --build
```

If Docker requires administrator permissions on Linux, use:

```bash
sudo docker compose up --build
```

This command:

* starts PostgreSQL 17;
* builds the backend Docker image;
* waits until PostgreSQL is healthy;
* applies Alembic migrations automatically;
* starts the FastAPI backend with Uvicorn.

When the backend is running, open:

```text
http://127.0.0.1:8000/docs
```

To stop the services:

```bash
docker compose down
```

If Docker requires administrator permissions:

```bash
sudo docker compose down
```

To stop the services and remove the local PostgreSQL volume:

```bash
docker compose down -v
```

If Docker requires administrator permissions:

```bash
sudo docker compose down -v
```

> Removing the volume permanently deletes local PostgreSQL data.

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

## Manual Backend Setup

Docker Compose is the recommended way to start the backend locally.

The following manual setup is useful when developing the backend directly on the host machine without running the backend inside Docker.

### 1. Create a Python virtual environment

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

### 2. Install backend dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

### 3. Create the backend environment file

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

### 4. Start PostgreSQL only

From the repository root:

```bash
docker compose up -d postgres
```

If Docker requires administrator permissions:

```bash
sudo docker compose up -d postgres
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

### 5. Apply database migrations

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

### 6. Run the FastAPI backend manually

From the `backend` directory:

```bash
python -m uvicorn app.main:app --reload
```

The backend is available at:

```text
http://127.0.0.1:8000
```

## Running Tests

Before running tests, make sure test database configuration is available.

From the `backend` directory:

```bash
export DATABASE_URL=postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test
export TEST_DATABASE_URL=postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test
```

Run tests:

```bash
python -m pytest -v
```

Run tests with coverage:

```bash
python -m pytest -v --cov=app --cov-report=term-missing
```

## Code Quality

Run Ruff lint check:

```bash
python -m ruff check backend
```

Run Ruff format check:

```bash
python -m ruff format --check backend
```

Apply Ruff formatting:

```bash
python -m ruff format backend
```

## Database Migrations

From the `backend` directory:

```bash
alembic upgrade head
```

Check whether models and migrations are synchronized:

```bash
alembic check
```

Create a new migration after changing SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe migration"
```

## Docker

### Build backend image

From the repository root:

```bash
docker build -t mealio-backend ./backend
```

If Docker requires administrator permissions:

```bash
sudo docker build -t mealio-backend ./backend
```

### Run backend image manually

```bash
docker run --rm -p 8000:8000 mealio-backend
```

For normal local development, use Docker Compose instead because it also starts PostgreSQL and applies migrations.

## Continuous Integration

The backend CI workflow runs on pull requests to `main` and pushes to `main`.

The workflow includes:

* backend quality checks;
* Ruff lint check;
* Ruff format check;
* PostgreSQL service for tests;
* Alembic migrations;
* Alembic migration state check;
* pytest test suite;
* pytest coverage report;
* backend Docker image build check.

## Git Workflow

Development is organized with issues, branches, pull requests, and squash merges.

Typical workflow:

```bash
git checkout main
git pull
git checkout -b type/short-description
```

After making changes:

```bash
git status
git add .
git commit -m "type: short description"
git push -u origin type/short-description
```

Then open a pull request into `main`.

## Notes

This project is actively evolving as part of a Bachelor's Thesis.

The current priority is building a stable backend foundation with clean architecture, database migrations, automated tests, Docker support, and CI checks before completing the mobile client and AI features.
