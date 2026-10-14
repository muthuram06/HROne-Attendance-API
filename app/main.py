"""HROne Employee Attendance & Analytics API."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "attendance_db").strip()

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

PRESENCE = ("PRESENT", "WFH", "ON_DUTY")
STATUSES = (*PRESENCE, "ABSENT", "LEAVE")

EPOCH_MIN = 100_000_000_000
EPOCH_MAX = 4_102_444_800_000

app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
)

STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

_client: MongoClient | None = None
_db = None
_indexes_ready = False


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------

class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class EmployeeCreate(StrictModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(
        max_length=120,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(
        default="09:30",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    shift_end: str = Field(
        default="18:30",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    joined_on: str

    @field_validator("joined_on")
    @classmethod
    def validate_joined_on(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("joined_on must be YYYY-MM-DD") from exc

        if parsed.isoformat() != value:
            raise ValueError("joined_on must be YYYY-MM-DD")

        return value

    @field_validator("name", "department")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_shift(self):
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self


class PunchInRequest(StrictModel):
    emp_code: str = Field(min_length=1)
    punched_at: StrictInt | None = Field(
        default=None,
        ge=EPOCH_MIN,
        le=EPOCH_MAX,
    )
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"


class PunchOutRequest(StrictModel):
    emp_code: str = Field(min_length=1)
    punched_at: StrictInt | None = Field(
        default=None,
        ge=EPOCH_MIN,
        le=EPOCH_MAX,
    )


class RegularizeRequest(StrictModel):
    status: Literal[
        "PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"
    ] | None = None

    punch_in: StrictInt | None = Field(
        default=None,
        ge=EPOCH_MIN,
        le=EPOCH_MAX,
    )
    punch_out: StrictInt | None = Field(
        default=None,
        ge=EPOCH_MIN,
        le=EPOCH_MAX,
    )
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

    @field_validator("reason", "regularized_by")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field must not be blank")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, values):
        if isinstance(values, dict):
            if "status" in values and values["status"] is None:
                raise ValueError("status cannot be null")

            for field in ("punch_in", "punch_out"):
                if field in values and values[field] is None:
                    raise ValueError(
                        f"{field} cannot be null; omit it to leave unchanged"
                    )

        return values


# ---------------------------------------------------------------------
# Date/time and attendance calculations
# ---------------------------------------------------------------------

def round_half_up(value, places: int = 2) -> float:
    quantum = Decimal("1").scaleb(-places)
    return float(
        Decimal(str(value)).quantize(
            quantum,
            rounding=ROUND_HALF_UP,
        )
    )


def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def to_datetime(epoch_ms: int | None) -> datetime | None:
    if epoch_ms is None:
        return None

    if (
        isinstance(epoch_ms, bool)
        or not isinstance(epoch_ms, int)
        or not EPOCH_MIN <= epoch_ms <= EPOCH_MAX
    ):
        raise HTTPException(
            status_code=422,
            detail="Timestamp must be integer epoch milliseconds",
        )

    # Contract rule: truncate timestamps to whole seconds.
    return datetime.fromtimestamp(epoch_ms // 1000, tz=UTC)


def to_epoch_ms(value: datetime | None) -> int | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return int(value.timestamp()) * 1000


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def attendance_date(punch_in: datetime, employee: dict) -> str:
    """Resolve the attendance date using the employee's shift and IST."""
    local = as_utc(punch_in).astimezone(IST)

    start = time.fromisoformat(employee["shift_start"])
    end = time.fromisoformat(employee["shift_end"])

    day = local.date()

    # For an overnight shift, punches after midnight before shift end
    # belong to the previous attendance date.
    if end <= start and local.time().replace(tzinfo=None) < end:
        day -= timedelta(days=1)

    return day.isoformat()


def shift_start_datetime(day: str, employee: dict) -> datetime:
    local = datetime.combine(
        date.fromisoformat(day),
        time.fromisoformat(employee["shift_start"]),
        IST,
    )
    return local.astimezone(UTC)


def shift_end_datetime(day: str, employee: dict) -> datetime:
    day_value = date.fromisoformat(day)

    start = time.fromisoformat(employee["shift_start"])
    end = time.fromisoformat(employee["shift_end"])

    if end <= start:
        day_value += timedelta(days=1)

    local = datetime.combine(day_value, end, IST)
    return local.astimezone(UTC)


def compute_late_minutes(
    punch_in: datetime | None,
    day: str,
    employee: dict,
) -> int:
    if punch_in is None:
        return 0

    seconds_late = int(
        (as_utc(punch_in) - shift_start_datetime(day, employee))
        .total_seconds()
    )

    # A 10-minute grace period applies. Late starts must be strictly
    # more than 10 minutes after shift start.
    return seconds_late // 60 if seconds_late > 600 else 0


def compute_derived(
    day: str,
    employee: dict,
    punch_in: datetime | None,
    punch_out: datetime | None,
) -> dict:
    late_minutes = compute_late_minutes(punch_in, day, employee)

    if punch_in is None or punch_out is None:
        return {
            "late_minutes": late_minutes,
            "work_hours": None,
            "overtime_minutes": 0,
            "half_day": False,
        }

    seconds = int(
        (as_utc(punch_out) - as_utc(punch_in)).total_seconds()
    )

    work_hours = round_half_up(
        Decimal(seconds) / Decimal(3600),
        2,
    )

    overtime_seconds = int(
        (
            as_utc(punch_out)
            - shift_end_datetime(day, employee)
        ).total_seconds()
    )

    # Overtime begins only when the employee works at least 30 minutes
    # beyond the scheduled shift end.
    overtime_minutes = (
        overtime_seconds // 60
        if overtime_seconds >= 1800
        else 0
    )

    return {
        "late_minutes": late_minutes,
        "work_hours": work_hours,
        "overtime_minutes": overtime_minutes,
        "half_day": work_hours < 4.50,
    }


def valid_month(month: str):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "month must be YYYY-MM")

    year, month_number = map(int, month.split("-"))
    first = date(year, month_number, 1)

    if month_number == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month_number + 1, 1)

    last = next_first - timedelta(days=1)

    return first.isoformat(), last.isoformat(), first, last


def working_days(start: date, end: date) -> int:
    """Count Monday-Friday dates inclusively."""
    if end < start:
        return 0

    full_weeks, remaining = divmod((end - start).days + 1, 7)
    count = full_weeks * 5

    for offset in range(remaining):
        day = start + timedelta(days=full_weeks * 7 + offset)
        if day.weekday() < 5:
            count += 1

    return count


# ---------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------

def serialize_history(history: list | None) -> list:
    output = []

    for entry in history or []:
        changes = {}

        for field, values in (entry.get("changes") or {}).items():
            changes[field] = {
                "from": (
                    to_epoch_ms(values.get("from"))
                    if field in ("punch_in", "punch_out")
                    else values.get("from")
                ),
                "to": (
                    to_epoch_ms(values.get("to"))
                    if field in ("punch_in", "punch_out")
                    else values.get("to")
                ),
            }

        output.append({
            "at": to_epoch_ms(entry.get("at")),
            "by": entry.get("by"),
            "reason": entry.get("reason"),
            "changes": changes,
        })

    return output


def serialize_employee(doc: dict) -> dict:
    return {
        key: (
            to_epoch_ms(value)
            if key == "created_at"
            else value
        )
        for key, value in doc.items()
        if key != "_id"
    }


def serialize_attendance(doc: dict) -> dict:
    return {
        "emp_code": doc["emp_code"],
        "date": doc["date"],
        "status": doc["status"],
        "punch_in": to_epoch_ms(doc.get("punch_in")),
        "punch_out": to_epoch_ms(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": int(doc.get("late_minutes", 0) or 0),
        "overtime_minutes": int(
            doc.get("overtime_minutes", 0) or 0
        ),
        "half_day": bool(doc.get("half_day", False)),
        "history": serialize_history(doc.get("history", [])),
    }


# ---------------------------------------------------------------------
# MongoDB connection and indexes
# ---------------------------------------------------------------------

def get_database():
    global _client, _db, _indexes_ready

    if _db is not None and _indexes_ready:
        try:
            _client.admin.command("ping")
            return _db
        except PyMongoError:
            _db = None
            _indexes_ready = False

    if not MONGO_URI:
        raise HTTPException(
            status_code=503,
            detail="MONGO_URI is not configured",
        )

    try:
        if _client is None:
            _client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                tz_aware=False,
            )

        _client.admin.command("ping")
        _db = _client[MONGO_DB]

        if not _indexes_ready:
            _db.employees.create_index(
                [("emp_code", ASCENDING)],
                unique=True,
                name="uq_employee_code",
            )
            _db.employees.create_index(
                [("department", ASCENDING), ("joined_on", ASCENDING)],
                name="department_joined",
            )
            _db.employees.create_index(
                [("joined_on", ASCENDING)],
                name="employee_joined_on",
            )
            _db.attendance_logs.create_index(
                [("emp_code", ASCENDING), ("date", DESCENDING)],
                unique=True,
                name="uq_attendance_employee_date",
            )
            _db.attendance_logs.create_index(
                [("date", DESCENDING), ("emp_code", ASCENDING)],
                name="attendance_date_employee",
            )
            _db.attendance_logs.create_index(
                [
                    ("date", ASCENDING),
                    ("status", ASCENDING),
                    ("late_minutes", DESCENDING),
                ],
                name="attendance_date_status_late",
            )
            _db.attendance_logs.create_index(
                [
                    ("status", ASCENDING),
                    ("date", DESCENDING),
                    ("emp_code", ASCENDING),
                ],
                name="attendance_status_date_employee",
            )

            _indexes_ready = True

        return _db

    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable",
        ) from exc


def employee_or_404(db, emp_code: str) -> dict:
    employee = db.employees.find_one(
        {"emp_code": emp_code},
        {"_id": 0},
    )

    if employee is None:
        raise HTTPException(404, "Employee not found")

    return employee


def presence_expr() -> dict:
    return {"$in": ["$status", list(PRESENCE)]}


# ---------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "HROne Attendance API is running",
        "dashboard": "/dashboard",
        "docs": "/docs",
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    path = STATIC_DIR / "index.html"

    if not path.exists():
        raise HTTPException(404, "Dashboard assets are not installed")

    return FileResponse(path)


@app.get("/health")
def health():
    db = get_database()

    try:
        db.command("ping")
    except PyMongoError as exc:
        raise HTTPException(
            503,
            "MongoDB is unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
    }


# ---------------------------------------------------------------------
# Employee endpoints
# ---------------------------------------------------------------------

@app.post("/employees", status_code=201)
def create_employee(body: EmployeeCreate):
    db = get_database()

    doc = body.model_dump()
    doc["emp_code"] = doc["emp_code"].strip()
    doc["name"] = doc["name"].strip()
    doc["email"] = doc["email"].strip().lower()
    doc["department"] = doc["department"].strip()
    doc["created_at"] = now_utc()

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            409,
            "Employee code already exists",
        ) from exc

    return serialize_employee(doc)


@app.get("/employees")
def list_employees(
    department: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    db = get_database()
    query = {"department": department} if department else {}

    total = db.employees.count_documents(query)

    cursor = (
        db.employees.find(query, {"_id": 0})
        .sort("emp_code", ASCENDING)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    return {
        "items": [serialize_employee(doc) for doc in cursor],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------
# Attendance endpoints
# ---------------------------------------------------------------------

@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInRequest):
    db = get_database()
    employee = employee_or_404(db, body.emp_code)

    punched_at = (
        to_datetime(body.punched_at)
        if body.punched_at is not None
        else now_utc()
    )

    day = attendance_date(punched_at, employee)
    derived = compute_derived(day, employee, punched_at, None)

    doc = {
        "emp_code": body.emp_code,
        "date": day,
        "status": body.status,
        "punch_in": punched_at,
        "punch_out": None,
        **derived,
        "history": [],
    }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            409,
            "Already punched in for this attendance date",
        ) from exc

    return serialize_attendance(doc)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutRequest):
    db = get_database()
    employee = employee_or_404(db, body.emp_code)

    punched_at = (
        to_datetime(body.punched_at)
        if body.punched_at is not None
        else now_utc()
    )

    # Find the most recent punch-in not later than the requested
    # punch-out time. This supports overnight shifts.
    record = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "punch_in": {"$ne": None, "$lte": punched_at},
        },
        sort=[("punch_in", DESCENDING)],
    )

    if record is None:
        raise HTTPException(404, "No eligible punch-in record found")

    punch_in_at = as_utc(record.get("punch_in"))

    if record.get("punch_out") is not None:
        raise HTTPException(409, "Already punched out")

    elapsed = (punched_at - punch_in_at).total_seconds()

    if elapsed <= 0 or elapsed > 86400:
        raise HTTPException(
            422,
            "Punch-out must be after punch-in and within 24 hours",
        )

    derived = compute_derived(
        record["date"],
        employee,
        punch_in_at,
        punched_at,
    )

    # Atomic condition means only one concurrent punch-out succeeds.
    updated = db.attendance_logs.find_one_and_update(
        {
            "_id": record["_id"],
            "punch_out": None,
        },
        {
            "$set": {
                "punch_out": punched_at,
                **derived,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(
            409,
            "Attendance record has already been punched out",
        )

    return serialize_attendance(updated)


@app.get("/attendance")
def list_attendance(
    emp_code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if status is not None and status not in STATUSES:
        raise HTTPException(422, "Invalid attendance status")

    for value, label in (
        (date_from, "date_from"),
        (date_to, "date_to"),
    ):
        if value is not None:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise HTTPException(
                    422,
                    f"{label} must be YYYY-MM-DD",
                ) from exc

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            422,
            "date_from must be on or before date_to",
        )

    query = {}

    if emp_code:
        query["emp_code"] = emp_code

    if date_from or date_to:
        query["date"] = {}

        if date_from:
            query["date"]["$gte"] = date_from

        if date_to:
            query["date"]["$lte"] = date_to

    if status:
        query["status"] = status

    db = get_database()
    total = db.attendance_logs.count_documents(query)

    cursor = (
        db.attendance_logs.find(query)
        .sort([("date", DESCENDING), ("emp_code", ASCENDING)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    return {
        "items": [serialize_attendance(doc) for doc in cursor],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------
# Manual corrections with audit history
# ---------------------------------------------------------------------

@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str,
    date: str,
    body: RegularizeRequest,
):
    try:
        if datetime.strptime(date, "%Y-%m-%d").date().isoformat() != date:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            422,
            "date must be YYYY-MM-DD",
        ) from exc

    db = get_database()
    employee = employee_or_404(db, emp_code)
    query = {"emp_code": emp_code, "date": date}
    current = db.attendance_logs.find_one(query)

    if current is None:
        raise HTTPException(404, "Attendance record not found")

    patch = body.model_dump(exclude_unset=True)
    reason = patch.pop("reason")
    regularized_by = patch.pop("regularized_by")

    if not patch:
        raise HTTPException(
            422,
            "No attendance fields were supplied",
        )

    old_status = current.get("status", "PRESENT")
    old_in = as_utc(current.get("punch_in"))
    old_out = as_utc(current.get("punch_out"))

    new_status = patch.get("status", old_status)

    new_in = (
        to_datetime(patch["punch_in"])
        if "punch_in" in patch
        else old_in
    )
    new_out = (
        to_datetime(patch["punch_out"])
        if "punch_out" in patch
        else old_out
    )

    if new_status in ("ABSENT", "LEAVE"):
        if "punch_in" in patch or "punch_out" in patch:
            raise HTTPException(
                422,
                "ABSENT and LEAVE cannot be supplied with punch times",
            )

        new_in, new_out = None, None

    elif new_in is None:
        raise HTTPException(
            422,
            "Presence status requires punch_in",
        )

    if new_in is not None and attendance_date(new_in, employee) != date:
        raise HTTPException(
            422,
            "punch_in must belong to the attendance date",
        )

    if new_out is not None:
        if (
            new_in is None
            or new_out <= new_in
            or (new_out - new_in).total_seconds() > 86400
        ):
            raise HTTPException(
                422,
                "punch_out must be after punch_in and within 24 hours",
            )

    if new_status in PRESENCE:
        derived = compute_derived(date, employee, new_in, new_out)
    else:
        derived = {
            "late_minutes": 0,
            "work_hours": None,
            "overtime_minutes": 0,
            "half_day": False,
        }

    new_values = {
        "status": new_status,
        "punch_in": new_in,
        "punch_out": new_out,
        **derived,
    }

    old_values = {
        "status": old_status,
        "punch_in": old_in,
        "punch_out": old_out,
        "late_minutes": int(current.get("late_minutes", 0) or 0),
        "work_hours": current.get("work_hours"),
        "overtime_minutes": int(
            current.get("overtime_minutes", 0) or 0
        ),
        "half_day": bool(current.get("half_day", False)),
    }

    changes = {}

    for field, new_value in new_values.items():
        old_value = old_values.get(field)

        if field in ("punch_in", "punch_out"):
            old_value = as_utc(old_value)
            new_value = as_utc(new_value)

        if old_value != new_value:
            changes[field] = {
                "from": old_values.get(field),
                "to": new_values[field],
            }

    if not changes:
        raise HTTPException(
            422,
            "Correction does not change the record",
        )

    compare = {
        "emp_code": emp_code,
        "date": date,
        "status": current.get("status"),
        "punch_in": current.get("punch_in"),
        "punch_out": current.get("punch_out"),
        "history": current.get("history", []),
    }

    entry = {
        "at": now_utc(),
        "by": regularized_by,
        "reason": reason,
        "changes": changes,
    }

    updated = db.attendance_logs.find_one_and_update(
        compare,
        {
            "$set": new_values,
            "$push": {"history": entry},
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(
            409,
            "Attendance record changed concurrently; reload and retry",
        )

    return serialize_attendance(updated)


# ---------------------------------------------------------------------
# Analytics: employee monthly summary
# ---------------------------------------------------------------------

@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str,
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    db = get_database()
    employee = employee_or_404(db, emp_code)
    first, last, first_date, last_date = valid_month(month)

    joined = date.fromisoformat(employee["joined_on"])
    work_start = max(first_date, joined)
    days = working_days(work_start, last_date)

    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {"$gte": first, "$lte": last},
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", list(PRESENCE)]},
                                    {
                                        "$gt": [
                                            {
                                                "$dayOfWeek": {
                                                    "$dateFromString": {
                                                        "dateString": "$date"
                                                    }
                                                }
                                            },
                                            1,
                                        ]
                                    },
                                    {
                                        "$lt": [
                                            {
                                                "$dayOfWeek": {
                                                    "$dateFromString": {
                                                        "dateString": "$date"
                                                    }
                                                }
                                            },
                                            7,
                                        ]
                                    },
                                ]
                            },
                            {
                                "$cond": [
                                    {"$eq": ["$half_day", True]},
                                    0.5,
                                    1,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "LEAVE"]},
                            1,
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                },
            }
        },
    ]

    rows = list(db.attendance_logs.aggregate(pipeline))
    row = rows[0] if rows else {}

    present_days = float(row.get("present_days", 0))

    percentage = (
        round_half_up(
            Decimal(str(present_days)) / Decimal(days) * 100,
            4,
        )
        if days
        else None
    )

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": days,
        "present_days": present_days,
        "leave_days": row.get("leave_days", 0),
        "late_count": row.get("late_count", 0),
        "total_late_minutes": row.get("total_late_minutes", 0),
        "total_overtime_minutes": row.get(
            "total_overtime_minutes", 0
        ),
        "attendance_pct": percentage,
    }


# ---------------------------------------------------------------------
# Analytics: department summary
# ---------------------------------------------------------------------

@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: str | None = None,
):
    db = get_database()
    first, last, _, _ = valid_month(month)

    employee_match = {"joined_on": {"$lte": last}}

    if department:
        employee_match["department"] = department

    pipeline = [
        {"$match": employee_match},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$code"]},
                                    {"$gte": ["$date", first]},
                                    {"$lte": ["$date", last]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {
            "$addFields": {
                "_present_days": {
                    "$sum": {
                        "$map": {
                            "input": {
                                "$filter": {
                                    "input": "$logs",
                                    "as": "log",
                                    "cond": {
                                        "$in": [
                                            "$$log.status",
                                            list(PRESENCE),
                                        ]
                                    },
                                }
                            },
                            "as": "log",
                            "in": {
                                "$cond": [
                                    {"$eq": ["$$log.half_day", True]},
                                    0.5,
                                    1,
                                ]
                            },
                        }
                    }
                },
                "_work_logs": {
                    "$filter": {
                        "input": "$logs",
                        "as": "log",
                        "cond": {
                            "$and": [
                                {
                                    "$in": [
                                        "$$log.status",
                                        list(PRESENCE),
                                    ]
                                },
                                {"$ne": ["$$log.work_hours", None]},
                            ]
                        },
                    }
                },
                "_late_count": {
                    "$size": {
                        "$filter": {
                            "input": "$logs",
                            "as": "log",
                            "cond": {"$gt": ["$$log.late_minutes", 0]},
                        }
                    }
                },
                "_late_minutes": {
                    "$sum": {
                        "$map": {
                            "input": "$logs",
                            "as": "log",
                            "in": {"$ifNull": ["$$log.late_minutes", 0]},
                        }
                    }
                },
                "_leave_count": {
                    "$size": {
                        "$filter": {
                            "input": "$logs",
                            "as": "log",
                            "cond": {"$eq": ["$$log.status", "LEAVE"]},
                        }
                    }
                },
                "_on_duty_count": {
                    "$size": {
                        "$filter": {
                            "input": "$logs",
                            "as": "log",
                            "cond": {"$eq": ["$$log.status", "ON_DUTY"]},
                        }
                    }
                },
            }
        },
        {
            "$addFields": {
                "_work_sum": {
                    "$sum": {
                        "$map": {
                            "input": "$_work_logs",
                            "as": "log",
                            "in": "$$log.work_hours",
                        }
                    }
                },
                "_work_count": {"$size": "$_work_logs"},
            }
        },
        {
            "$group": {
                "_id": "$department",
                "headcount": {"$sum": 1},
                "present_days": {"$sum": "$_present_days"},
                "_work_sum": {"$sum": "$_work_sum"},
                "_work_count": {"$sum": "$_work_count"},
                "late_count": {"$sum": "$_late_count"},
                "total_late_minutes": {"$sum": "$_late_minutes"},
                "leave_count": {"$sum": "$_leave_count"},
                "on_duty_count": {"$sum": "$_on_duty_count"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": 1,
                "present_days": 1,
                "avg_work_hours": {
                    "$cond": [
                        {"$gt": ["$_work_count", 0]},
                        {"$divide": ["$_work_sum", "$_work_count"]},
                        None,
                    ]
                },
                "late_count": 1,
                "total_late_minutes": 1,
                "leave_count": 1,
                "on_duty_count": 1,
            }
        },
        {"$sort": {"department": 1}},
    ]

    items = list(db.employees.aggregate(pipeline))

    for item in items:
        if item["avg_work_hours"] is not None:
            item["avg_work_hours"] = round_half_up(
                item["avg_work_hours"], 2
            )
        item["present_days"] = float(item["present_days"])

    return {"month": month, "items": items}


# ---------------------------------------------------------------------
# Analytics: late leaderboard
# ---------------------------------------------------------------------

@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(10, ge=1, le=50),
    department: str | None = None,
):
    db = get_database()
    first, last, _, _ = valid_month(month)

    pipeline = [
        {
            "$match": {
                "date": {"$gte": first, "$lte": last},
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
    ]

    if department:
        pipeline.append({"$match": {"employee.department": department}})

    pipeline.extend([
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}},
            }
        },
        {"$match": {"rank": {"$lte": limit}}},
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
        {
            "$project": {
                "_id": 0,
                "rank": 1,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "total_late_minutes": 1,
                "late_count": 1,
            }
        },
    ])

    return {
        "month": month,
        "items": list(db.attendance_logs.aggregate(pipeline)),
    }


# ---------------------------------------------------------------------
# Analytics: department trend
# ---------------------------------------------------------------------

@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
):
    try:
        start = date.fromisoformat(from_)
        end = date.fromisoformat(to)

        if start.isoformat() != from_ or end.isoformat() != to:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            422,
            "from and to must be YYYY-MM-DD",
        ) from exc

    if end < start:
        raise HTTPException(422, "to must be on or after from")

    if (end - start).days + 1 > 92:
        raise HTTPException(
            422,
            "Trend range cannot exceed 92 days",
        )

    db = get_database()

    if db.employees.count_documents({"department": department}) == 0:
        raise HTTPException(404, "Department not found")

    start_dt = datetime.combine(start, time.min, UTC)
    end_dt = datetime.combine(end, time.min, UTC)

    pipeline = [
        {"$documents": [{"_start": start_dt, "_end": end_dt}]},
        {
            "$project": {
                "days": {
                    "$map": {
                        "input": {
                            "$range": [
                                0,
                                {
                                    "$add": [
                                        {
                                            "$dateDiff": {
                                                "startDate": "$_start",
                                                "endDate": "$_end",
                                                "unit": "day",
                                            }
                                        },
                                        1,
                                    ]
                                },
                            ]
                        },
                        "as": "n",
                        "in": {
                            "$dateAdd": {
                                "startDate": "$_start",
                                "unit": "day",
                                "amount": "$$n",
                            }
                        },
                    }
                }
            }
        },
        {"$unwind": "$days"},
        {
            "$set": {
                "day": "$days",
                "date": {
                    "$dateToString": {
                        "date": "$days",
                        "format": "%Y-%m-%d",
                        "timezone": "UTC",
                    }
                },
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {"daystr": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$department", department]},
                                    {"$lte": ["$joined_on", "$$daystr"]},
                                ]
                            }
                        }
                    },
                    {"$project": {"_id": 0, "emp_code": 1}},
                ],
                "as": "eligible",
            }
        },
        {
            "$set": {
                "headcount": {"$size": "$eligible"},
                "is_working_day": {
                    "$not": [
                        {"$in": [{"$dayOfWeek": "$day"}, [1, 7]]}
                    ]
                },
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {
                    "daystr": "$date",
                    "codes": {
                        "$map": {
                            "input": "$eligible",
                            "as": "employee",
                            "in": "$$employee.emp_code",
                        }
                    },
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$date", "$$daystr"]},
                                    {"$in": ["$emp_code", "$$codes"]},
                                ]
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "present_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$in": ["$status", list(PRESENCE)]},
                                        {
                                            "$cond": [
                                                {"$eq": ["$half_day", True]},
                                                0.5,
                                                1,
                                            ]
                                        },
                                        0,
                                    ]
                                }
                            },
                            "late_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$gt": ["$late_minutes", 0]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                ],
                "as": "daily",
            }
        },
        {
            "$set": {
                "present_count": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$daily.present_count", 0]},
                        0,
                    ]
                },
                "late_count": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$daily.late_count", 0]},
                        0,
                    ]
                },
            }
        },
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {"$divide": ["$present_count", "$headcount"]},
                        None,
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"day": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": 1,
            }
        },
        {"$sort": {"date": 1}},
    ]

    items = list(db.aggregate(pipeline))

    for item in items:
        item["present_count"] = float(item["present_count"])

        if item["attendance_rate"] is not None:
            item["attendance_rate"] = round_half_up(
                item["attendance_rate"], 4
            )

        if item["moving_avg_7d"] is not None:
            item["moving_avg_7d"] = round_half_up(
                item["moving_avg_7d"], 4
            )

    return {"department": department, "items": items}


# ---------------------------------------------------------------------
# MongoDB explain endpoint
# ---------------------------------------------------------------------

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str,
    emp_code: str | None = None,
    month: str | None = None,
    department: str | None = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    db = get_database()

    if endpoint == "attendance_list":
        query = {}

        if emp_code:
            query["emp_code"] = emp_code

        if status:
            if status not in STATUSES:
                raise HTTPException(422, "Invalid status")
            query["status"] = status

        if date_from or date_to:
            query["date"] = {}

            if date_from:
                query["date"]["$gte"] = date_from

            if date_to:
                query["date"]["$lte"] = date_to

        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "date_from must be <= date_to")

        explanation = db.command({
            "explain": {
                "find": "attendance_logs",
                "filter": query,
                "sort": {"date": -1, "emp_code": 1},
                "skip": (page - 1) * page_size,
                "limit": page_size,
            },
            "verbosity": "executionStats",
        })

        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": explanation,
        }

    if endpoint == "department_trend":
        if not department or not from_ or not to:
            raise HTTPException(
                422,
                "department, from and to are required",
            )

        try:
            start = date.fromisoformat(from_)
            end = date.fromisoformat(to)
        except ValueError as exc:
            raise HTTPException(
                422,
                "from/to must be YYYY-MM-DD",
            ) from exc

        if end < start or (end - start).days + 1 > 92:
            raise HTTPException(422, "Invalid trend range")

        pipeline = [
            {"$match": {"date": {"$gte": from_, "$lte": to}}},
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
        ]

        explanation = db.command({
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        })

        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": explanation,
        }

    if not month:
        raise HTTPException(422, "month is required")

    first, last, _, _ = valid_month(month)

    if endpoint == "employee_monthly":
        if not emp_code:
            raise HTTPException(422, "emp_code is required")

        pipeline = [
            {
                "$match": {
                    "emp_code": emp_code,
                    "date": {"$gte": first, "$lte": last},
                }
            },
            {"$group": {"_id": "$emp_code", "records": {"$sum": 1}}},
        ]
        collection = "attendance_logs"

    elif endpoint == "department_summary":
        match = {"joined_on": {"$lte": last}}

        if department:
            match["department"] = department

        pipeline = [
            {"$match": match},
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "let": {"code": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$emp_code", "$$code"]},
                                        {"$gte": ["$date", first]},
                                        {"$lte": ["$date", last]},
                                    ]
                                }
                            }
                        }
                    ],
                    "as": "logs",
                }
            },
        ]
        collection = "employees"

    elif endpoint == "late_leaderboard":
        pipeline = [
            {
                "$match": {
                    "date": {"$gte": first, "$lte": last},
                    "late_minutes": {"$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {"$sum": "$late_minutes"},
                }
            },
        ]
        collection = "attendance_logs"

    else:
        raise HTTPException(422, "Unknown endpoint")

    explanation = db.command({
        "explain": {
            "aggregate": collection,
            "pipeline": pipeline,
            "cursor": {},
        },
        "verbosity": "executionStats",
    })

    return {
        "endpoint": endpoint,
        "collection": collection,
        "explain": explanation,
    }