# HROne Attendance API

A REST API for employee management, attendance tracking, attendance regularization, and attendance analytics. Built with Python, FastAPI, and MongoDB.

## Live Deployment

- **Live API:** https://hrone-attendance-api-5evn.onrender.com
- **Swagger UI:** https://hrone-attendance-api-5evn.onrender.com/docs
- **Health Check:** https://hrone-attendance-api-5evn.onrender.com/health

The API is deployed on Render and uses MongoDB for persistent storage. Swagger UI allows reviewers to explore endpoints, submit requests, and inspect responses.

## Features

- Create and list employees
- Employee attendance punch-in and punch-out
- Attendance listing with filtering and pagination
- Manual attendance corrections with an audit trail
- Working-hour and late-arrival calculations
- Monthly employee attendance analytics
- Department attendance summaries
- Late-arrival leaderboard
- Department attendance trends
- MongoDB indexes for data integrity and query performance
- Request validation and HTTP error handling
- Interactive API documentation
- Automated tests using pytest

## Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Backend language |
| FastAPI | REST API framework |
| MongoDB | Persistent database |
| PyMongo | MongoDB integration |
| Pydantic | Request validation |
| Uvicorn | ASGI server |
| Pytest | Automated testing |

## Project Structure

```text
HROne-Attendance-API/
├── app/
│   └── main.py
├── tests/
│   └── test_api.py
├── static/
│   ├── index.html
│   ├── dashboard.css
│   ├── dashboard.js
│   └── swagger.css
├── .env.example
├── .gitignore
├── README.md
├── REVIEW.md
├── DECISIONS.md
└── requirements.txt
```

The local `.venv/` directory and actual `.env` file must remain outside version control.

## Prerequisites

- Python 3.11 or later
- MongoDB Atlas or a compatible MongoDB instance
- Git

## Installation

Clone the repository:

```bash
git clone https://github.com/muthuram06/HROne-Attendance-API.git
cd HROne-Attendance-API
```

Create and activate a virtual environment on Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Environment Configuration

Create a local `.env` file in the project root. Configure the MongoDB connection string and database name using the environment variable names expected by `app/main.py`.

Example placeholders:

```env
MONGO_URI=your_mongodb_connection_string
MONGO_DB=attendance_db
```

Replace these placeholders with your own configuration. Do not commit the real `.env` file, database credentials, or passwords to GitHub.

For production, configure the required environment variables in the hosting provider's environment settings.

## Running the Application Locally

From the project root, activate the virtual environment and start the server:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Local URLs:

- API root: http://127.0.0.1:8000/
- Health check: http://127.0.0.1:8000/health
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Dashboard: http://127.0.0.1:8000/dashboard

Keep the terminal running while using the local application.

## API Endpoints

The following endpoints are available in the deployed API documentation.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | API root |
| GET | `/health` | Application and database health |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List employees |
| POST | `/attendance/punch-in` | Record punch-in |
| POST | `/attendance/punch-out` | Record punch-out |
| GET | `/attendance` | Retrieve attendance records |
| PATCH | `/attendance/{emp_code}/{date}` | Regularize an attendance record |
| GET | `/analytics/employees/{emp_code}/monthly` | Employee monthly analytics |
| GET | `/analytics/departments/summary` | Department attendance summary |
| GET | `/analytics/leaderboard/late` | Late-arrival leaderboard |
| GET | `/analytics/departments/{department}/trend` | Department attendance trend |
| GET | `/admin/explain/{endpoint}` | Explain an endpoint |

Refer to Swagger UI for exact request schemas, required parameters, response formats, and available status codes.

## Attendance Business Rules

The API implements attendance operations and calculations based on its configured business rules.

- Attendance dates use the configured timezone logic.
- Employee existence is checked before attendance operations.
- Duplicate attendance records are prevented through database constraints.
- Punch-in and punch-out operations validate attendance state.
- Working hours, lateness, overtime, and half-day status are calculated from attendance data and shift rules.
- Manual regularization records correction details in the attendance history.
- Analytics summarize attendance data for employees and departments.

See `DECISIONS.md` for design rationale and `REVIEW.md` for code review considerations.

## Running Tests

Run the automated test suite from the repository root:

```bash
python -m pytest -q
```

The tests cover API behavior and attendance-related validation and business rules.

## Deployment

The application is deployed on Render.

- **Service:** https://hrone-attendance-api-5evn.onrender.com
- **API documentation:** https://hrone-attendance-api-5evn.onrender.com/docs
- **Health endpoint:** https://hrone-attendance-api-5evn.onrender.com/health

Production start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Configure the MongoDB environment variables in Render. Never include secrets in source code or public documentation.

## Design Documentation

- **[REVIEW.md](REVIEW.md):** Code review findings covering validation, data integrity, attendance rules, audit history, analytics, error handling, and testing.
- **[DECISIONS.md](DECISIONS.md):** Design decisions covering the framework, database, timezone, attendance operations, analytics, security, and testing.

## Security

- Keep database credentials in environment variables.
- Exclude `.env` and `.venv/` from version control.
- Validate externally supplied data.
- Use suitable HTTP status codes for validation errors, conflicts, and missing resources.
- Avoid exposing credentials or internal exception details in API responses.

## License

This project was developed as an employee attendance API assignment.
