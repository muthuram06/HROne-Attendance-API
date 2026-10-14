# HROne Attendance API

A REST API for employee management, attendance tracking, manual attendance corrections, and attendance analytics. Built using **Python, FastAPI, and MongoDB**.

## Features

- Employee management and employee listing
- Attendance punch-in and punch-out
- Attendance history with pagination and filters
- Manual attendance corrections with an audit trail
- Attendance calculations, including working hours, late minutes, overtime, and half-day status
- Monthly employee attendance analytics
- Department attendance summaries
- Late-arrival leaderboard
- MongoDB-backed data storage and indexing
- Interactive API documentation through Swagger UI
- Automated API tests using pytest

## Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Backend language |
| FastAPI | REST API framework |
| MongoDB | Database |
| PyMongo | MongoDB integration |
| Pydantic | Request validation |
| Uvicorn | ASGI server |
| Pytest | Automated testing |

## Project Structure

```text
HROne-Attendance-API/
├── app/
│   ├── main.py
│   └── __pycache__/
├── static/
│   ├── index.html
│   ├── dashboard.css
│   ├── dashboard.js
│   └── swagger.css
├── tests/
│   └── test_api.py
├── .env.example
├── .gitignore
├── README.md
├── REVIEW.md
├── DECISIONS.md
└── requirements.txt
```

The `.venv/` directory and actual `.env` file should remain local and must not be committed to GitHub.

## Prerequisites

- Python 3.11 or later
- MongoDB 6.0+ or MongoDB Atlas
- Git

## Installation

Clone the repository:

```bash
git clone https://github.com/muthuram06/HROne-Attendance-API.git
cd HROne-Attendance-API
```

Create and activate a virtual environment on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Environment Configuration

Create a `.env` file in the project root and configure your MongoDB connection string and database name according to the environment variables read by `app/main.py`.

Example:

```env
MONGODB_URI=your_mongodb_connection_string
DATABASE_NAME=hrone_attendance
```

Use the exact environment variable names expected by your application. Never commit your actual `.env` file, MongoDB credentials, or passwords to a public repository.

## Running the Application

Start the development server:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at:

- API root: http://127.0.0.1:8000/
- Health check: http://127.0.0.1:8000/health
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Dashboard: http://127.0.0.1:8000/dashboard

Keep the terminal running while using these local URLs.

## API Endpoints

The implemented endpoint names and required parameters are defined by the running application's OpenAPI documentation at `/docs`.

The main API areas include:

| Area | Purpose |
|---|---|
| Employees | Create, list, retrieve, update, and delete employee records |
| Attendance | Punch-in, punch-out, and retrieve attendance records |
| Corrections | Update attendance records while preserving correction history |
| Employee analytics | Monthly attendance metrics for an employee |
| Department analytics | Attendance summaries by department |
| Late-arrival analytics | Rank employees by late arrivals |
| API documentation | Explore request schemas and responses through Swagger UI |

Use `/docs` to verify the exact routes, request bodies, query parameters, and response codes implemented in the current version.

## Attendance Business Rules

The API is designed to validate attendance requests and calculate derived attendance information consistently.

- Attendance dates and time calculations use the configured timezone rules.
- Duplicate attendance actions should be rejected.
- Punch-out times must be valid relative to punch-in times.
- Working hours, lateness, overtime, and half-day status are derived from attendance timestamps and applicable shift rules.
- Manual corrections should include a reason, editor information, and an audit history.
- Analytics should handle missing attendance data and employees with no attendance records.

Refer to `DECISIONS.md` and `REVIEW.md` for the design rationale and review considerations.

## Running Tests

Run the test suite from the project root:

```bash
python -m pytest -q
```

Tests should cover successful API requests, invalid inputs, duplicate attendance, punch-out validation, correction history, and analytics edge cases.

## Deployment

The application can be deployed to a Python-compatible hosting provider such as Render.

Configure the required MongoDB environment variables in the hosting provider's environment settings. Do not upload local secrets.

Example production start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Confirm that the selected hosting platform supports the configured start command and port handling.

## Design Documentation

- [`REVIEW.md`](REVIEW.md) — code review findings, validation, data integrity, audit history, and testing.
- [`DECISIONS.md`](DECISIONS.md) — framework, database, timezone, analytics, and security decisions.

## Security

- Keep database credentials in environment variables.
- Exclude `.env` and `.venv/` from version control.
- Validate all externally supplied input.
- Use appropriate error responses without exposing secrets or internal database details.

## License

This project was developed as an employee attendance API assignment. Add a license if you intend to distribute it under specific reuse terms.
