
# Design Decisions

## 1. Framework

FastAPI was selected because it provides request validation, HTTP status handling, and automatically generated OpenAPI documentation.

## 2. Database

MongoDB stores employee and attendance records. Database indexes support data integrity and improve common query operations.

## 3. Timezone and Timestamps

Attendance calculations use the Asia/Kolkata timezone. Timestamps are normalized consistently before calculating attendance dates, working hours, lateness, and overtime.

## 4. Employee and Attendance Separation

Employee information is stored separately from attendance records. This avoids repeating employee profile data in every attendance entry and allows attendance history to be queried independently.

## 5. Punch-In and Punch-Out

Punch-in and punch-out operations validate employee existence and the current attendance state. Duplicate actions and invalid timestamps must be rejected.

Unique indexes and atomic database operations help protect against concurrent requests.

## 6. Manual Corrections

Manual corrections require a reason and the identity of the person making the change. Derived fields are recalculated, and the correction is added to the audit history so changes remain traceable.

## 7. Analytics

MongoDB aggregation pipelines are used for attendance summaries, department statistics, late-arrival rankings, and department trends. This keeps analytical processing close to the stored data.

## 8. Error Handling

The API uses appropriate HTTP status codes to distinguish successful operations, validation errors, conflicts, and missing resources.

## 9. Configuration and Security

Database connection details are loaded from environment variables. `.env` files and credentials must never be committed to the public repository.

## 10. Testing

Automated tests verify endpoint behavior and business rules. The test suite should also cover boundary conditions, duplicate requests, correction history, and analytics calculations.
