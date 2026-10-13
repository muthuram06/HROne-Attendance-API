import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError


# -------------------- CONFIGURATION --------------------

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "attendance_db").strip()

IST = ZoneInfo("Asia/Kolkata")


# -------------------- APPLICATION --------------------

app = FastAPI(
    title="HROne Attendance API",
    description="Manage employees and their attendance records.",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
)

# Serve CSS, JavaScript and other frontend files.
app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "HROne Attendance API is running",
        "dashboard": "/dashboard",
        "docs": "/docs",
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")



@app.get("/docs", include_in_schema=False)
def custom_swagger_ui():
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="HROne Attendance API | API Documentation",
        swagger_ui_parameters={
            "docExpansion": "list",
            "defaultModelsExpandDepth": -1,
            "displayRequestDuration": True,
            "filter": True,
            "persistAuthorization": True,
        },
    )

    html = response.body.decode("utf-8")

    # Keep Swagger's default CSS and add our custom stylesheet.
    html = html.replace(
        "</head>",
        '<link rel="stylesheet" href="/static/swagger.css">\n</head>',
    )

    return HTMLResponse(content=html)



# -------------------- DATABASE STATE --------------------

client = None
db = None


# -------------------- REQUEST MODELS --------------------

class EmployeeCreate(BaseModel):
    employee_id: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    department: str = Field(min_length=1, max_length=100)
    designation: str = Field(min_length=1, max_length=100)


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[str] = Field(default=None, min_length=3, max_length=254)
    department: Optional[str] = Field(
        default=None, min_length=1, max_length=100
    )
    designation: Optional[str] = Field(
        default=None, min_length=1, max_length=100
    )


class AttendanceCheckIn(BaseModel):
    employee_id: str = Field(min_length=1, max_length=30)


class AttendanceCheckOut(BaseModel):
    employee_id: str = Field(min_length=1, max_length=30)


# -------------------- DATABASE --------------------

def get_database():
    global client, db

    if db is not None:
        return db

    if not MONGO_URI:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MONGO_URI is not configured",
        )

    try:
        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
        )
        client.admin.command("ping")

        db = client[MONGO_DB]

        db["employees"].create_index(
            [("employee_id", 1)],
            unique=True,
        )
        db["employees"].create_index(
            [("email", 1)],
            unique=True,
        )
        db["attendance"].create_index(
            [("employee_id", 1), ("attendance_date", 1)],
            unique=True,
        )

        return db

    except PyMongoError:
        if client is not None:
            client.close()

        client = None
        db = None

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "MongoDB is unavailable. Check your database configuration."
            ),
        )


def serialize_document(document):
    if document is None:
        return None

    document["_id"] = str(document["_id"])
    return document


def get_employee_or_404(database, employee_id):
    employee = database["employees"].find_one(
        {"employee_id": employee_id}
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return employee


# -------------------- HEALTH CHECK --------------------

@app.get("/health")
def health_check():
    database = get_database()
    database.command("ping")

    return {
        "status": "ok",
        "database": "connected",
    }


# -------------------- EMPLOYEE CRUD --------------------

@app.post("/employees", status_code=status.HTTP_201_CREATED)
def create_employee(employee: EmployeeCreate):
    database = get_database()
    collection = database["employees"]

    document = employee.model_dump()

    for field in (
        "employee_id",
        "email",
        "name",
        "department",
        "designation",
    ):
        document[field] = document[field].strip()

    document["email"] = document["email"].lower()

    if not all(
        document[field]
        for field in (
            "employee_id",
            "email",
            "name",
            "department",
            "designation",
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Employee fields cannot be blank",
        )

    document["created_at"] = datetime.now(timezone.utc)

    try:
        result = collection.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee ID or email already exists",
        )

    document["_id"] = result.inserted_id
    return serialize_document(document)


@app.get("/employees")
def list_employees():
    database = get_database()
    employees = database["employees"].find().sort("name", 1)

    return [
        serialize_document(employee)
        for employee in employees
    ]


@app.get("/employees/{employee_id}")
def get_employee(employee_id: str):
    database = get_database()
    employee = get_employee_or_404(database, employee_id)

    return serialize_document(employee)


@app.put("/employees/{employee_id}")
def update_employee(employee_id: str, updates: EmployeeUpdate):
    database = get_database()
    collection = database["employees"]

    existing = get_employee_or_404(database, employee_id)
    changes = updates.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    for field, value in changes.items():
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null",
            )

        changes[field] = value.strip()

        if not changes[field]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be blank",
            )

    if "email" in changes:
        changes["email"] = changes["email"].lower()

    try:
        collection.update_one(
            {"_id": existing["_id"]},
            {"$set": changes},
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee ID or email already exists",
        )

    updated = collection.find_one({"_id": existing["_id"]})
    return serialize_document(updated)


@app.delete("/employees/{employee_id}")
def delete_employee(employee_id: str):
    database = get_database()

    result = database["employees"].delete_one(
        {"employee_id": employee_id}
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return {"message": "Employee deleted successfully"}


# -------------------- ATTENDANCE CHECK-IN --------------------

@app.post(
    "/attendance/check-in",
    status_code=status.HTTP_201_CREATED,
)
def check_in(request: AttendanceCheckIn):
    database = get_database()
    employee_id = request.employee_id.strip()

    get_employee_or_404(database, employee_id)

    collection = database["attendance"]

    now = datetime.now(timezone.utc)
    today = now.astimezone(IST).date().isoformat()

    record = {
        "employee_id": employee_id,
        "attendance_date": today,
        "check_in": now,
        "check_out": None,
        "working_hours": None,
        "created_at": now,
    }

    try:
        result = collection.insert_one(record)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already marked for today",
        )

    record["_id"] = result.inserted_id
    return serialize_document(record)


# -------------------- ATTENDANCE CHECK-OUT --------------------

@app.post("/attendance/check-out")
def check_out(request: AttendanceCheckOut):
    database = get_database()
    employee_id = request.employee_id.strip()

    get_employee_or_404(database, employee_id)

    collection = database["attendance"]
    today = datetime.now(IST).date().isoformat()

    record = collection.find_one(
        {
            "employee_id": employee_id,
            "attendance_date": today,
        }
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check-in record found for today",
        )

    if record.get("check_out") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already checked out for today",
        )

    now = datetime.now(timezone.utc)
    check_in_time = record["check_in"]

    # PyMongo may return naive UTC datetimes by default.
    if check_in_time.tzinfo is None:
        check_in_time = check_in_time.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - check_in_time).total_seconds()

    if elapsed_seconds < 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Check-out cannot occur before check-in",
        )

    working_hours = round(elapsed_seconds / 3600, 2)

    # Atomic update prevents concurrent duplicate check-outs.
    updated = collection.find_one_and_update(
        {
            "_id": record["_id"],
            "check_out": None,
        },
        {
            "$set": {
                "check_out": now,
                "working_hours": working_hours,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance has already been checked out",
        )

    return serialize_document(updated)


# -------------------- ATTENDANCE HISTORY --------------------

@app.get("/attendance/{employee_id}")
def get_attendance(employee_id: str):
    database = get_database()
    get_employee_or_404(database, employee_id)

    records = database["attendance"].find(
        {"employee_id": employee_id}
    ).sort("attendance_date", -1)

    return [
        serialize_document(record)
        for record in records
    ]


# -------------------- ATTENDANCE SUMMARY --------------------

@app.get("/attendance/summary/{employee_id}")
def attendance_summary(employee_id: str):
    database = get_database()
    get_employee_or_404(database, employee_id)

    records = list(
        database["attendance"].find(
            {"employee_id": employee_id}
        )
    )

    completed = [
        record
        for record in records
        if record.get("working_hours") is not None
    ]

    total_hours = round(
        sum(record["working_hours"] for record in completed),
        2,
    )

    return {
        "employee_id": employee_id,
        "total_days": len(records),
        "completed_days": len(completed),
        "pending_check_outs": len(records) - len(completed),
        "total_working_hours": total_hours,
    }