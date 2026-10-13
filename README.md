# HROne Attendance API

**A RESTful employee attendance management system built with FastAPI and MongoDB.**

Manage employee records, track daily check-ins and check-outs, view attendance history, and calculate working hours through a documented REST API.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/MongoDB-Database-47A248?style=flat-square&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Tests-Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="Pytest">
</p>

---

## Overview

HROne Attendance API provides backend services for employee management and daily attendance tracking. It uses MongoDB for data persistence and FastAPI for request validation, API handling, and interactive documentation.

## Features

| Feature | Description |
|---|---|
| Employee management | Create, retrieve, update, and delete employee records |
| Check-in / Check-out | Record employee attendance times |
| Duplicate prevention | Prevent multiple daily check-in records |
| Attendance history | Retrieve attendance records by employee |
| Attendance summary | View completed days, pending check-outs, and working hours |
| Database health | Verify API and MongoDB connectivity |
| Timezone handling | IST attendance dates and UTC timestamps |
| API documentation | Explore and test endpoints with Swagger UI |

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Database:** MongoDB Atlas
- **Database driver:** PyMongo
- **Validation:** Pydantic
- **Testing:** Pytest, HTTPX
- **Configuration:** python-dotenv

## Project Structure

```text
HROne-Attendance-API/
├── app/
│   └── main.py
├── tests/
│   └── test_api.py
├── .env                 # Local secrets; not committed
├── .gitignore
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11 or newer
- A MongoDB Atlas account or accessible MongoDB instance
- Git

### 1. Clone the repository

```bash
git clone https://github.com/muthuram06/HROne-Attendance-API.git
cd HROne-Attendance-API
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
MONGO_URI=your_mongodb_connection_string
MONGO_DB=attendance_db
```

Replace the placeholder with your actual connection string. Keep `.env` private and never commit database credentials.

### 5. Run the API

```bash
python -m uvicorn app.main:app --reload
```

Open the following URLs:

| Resource | URL |
|---|---|
| API root | http://127.0.0.1:8000/ |
| Health check | http://127.0.0.1:8000/health |
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |

## API Reference

All endpoints are available through Swagger UI at `/docs`.

### Employee Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/employees` | Create an employee |
| `GET` | `/employees` | List employees |
| `GET` | `/employees/{employee_id}` | Retrieve an employee |
| `PUT` | `/employees/{employee_id}` | Update an employee |
| `DELETE` | `/employees/{employee_id}` | Delete an employee |

### Attendance Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/attendance/check-in` | Record daily check-in |
| `POST` | `/attendance/check-out` | Record check-out and calculate working hours |
| `GET` | `/attendance/{employee_id}` | Retrieve attendance history |
| `GET` | `/attendance/summary/{employee_id}` | Retrieve attendance summary |

### Example: Check In

**Request**

```http
POST /attendance/check-in
Content-Type: application/json
```

```json
{
  "employee_id": "EMP001"
}
```

The response depends on whether the employee exists and has already checked in for the current attendance date. Duplicate check-ins are rejected.

## Testing

Run the test suite:

```bash
python -m pytest -q
```

The current basic test suite checks the root endpoint and database health endpoint.

## Deployment

The API can be deployed as a Python web service on a compatible hosting platform.

For Render, use:

**Build command**

```bash
pip install -r requirements.txt
```

**Start command**

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Configure `MONGO_URI` and `MONGO_DB` in the hosting provider's environment settings. Verify database connectivity and the `/health` endpoint after deployment.

## Security Notes

- Store credentials in environment variables.
- Never commit `.env` or expose database passwords.
- Restrict MongoDB network access appropriately.
- Add authentication and authorization before using the API for real employee data.

## Repository

**GitHub:** [muthuram06/HROne-Attendance-API](https://github.com/muthuram06/HROne-Attendance-API)

---

<p align="center">
  Built with Python, FastAPI, and MongoDB.
</p>
