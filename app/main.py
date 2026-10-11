from fastapi import FastAPI

app = FastAPI(
    title="Employee Attendance API",
    description="Track employee check-ins, check-outs, and attendance summaries.",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}