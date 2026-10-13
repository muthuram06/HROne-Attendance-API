# HROne Attendance API

A REST API built with **FastAPI, Python, and MongoDB** to manage employees and track daily attendance.

## Features

- Employee creation, retrieval, updating, and deletion
- Employee check-in and check-out
- Duplicate daily check-in prevention
- Attendance history by employee
- Attendance summary with completed days, pending check-outs, and total working hours
- MongoDB integration and database health check
- IST-based attendance dates and UTC timestamps
- Interactive API documentation using Swagger UI

## Tech Stack

- Python 3.11+
- FastAPI
- MongoDB Atlas
- PyMongo
- Pydantic
- Pytest

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/muthuram06/HROne-Attendance-API.git
cd HROne-Attendance-API
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

Windows:

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

Replace the placeholder with your MongoDB connection string. Never commit `.env` or publish database credentials.

### 5. Start the API

```bash
python -m uvicorn app.main:app --reload
```

The API will be available at:

- API: http://127.0.0.1:8000
- Swagger documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | API welcome endpoint |
| GET | `/health` | Check API and database health |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List employees |
| GET | `/employees/{employee_id}` | Get an employee |
| PUT | `/employees/{employee_id}` | Update an employee |
| DELETE | `/employees/{employee_id}` | Delete an employee |
| POST | `/attendance/check-in` | Record check-in |
| POST | `/attendance/check-out` | Record check-out |
| GET | `/attendance/{employee_id}` | Retrieve attendance history |
| GET | `/attendance/summary/{employee_id}` | Retrieve attendance summary |

Use `/docs` to inspect request schemas, execute requests, and view responses.

## Run Tests

```bash
python -m pytest -q
```

## Deployment

The API can be deployed to a Python-compatible hosting platform such as Render.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Configure `MONGO_URI` and `MONGO_DB` as environment variables in the hosting dashboard.

After deployment, verify the `/health` endpoint and test the API through `/docs`.

## Repository

GitHub: https://github.com/muthuram06/HROne-Attendance-API
