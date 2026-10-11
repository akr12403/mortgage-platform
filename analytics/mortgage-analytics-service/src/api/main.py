from fastapi import FastAPI

app = FastAPI(
    title="Mortgage Analytics Service",
    description="Python analytics and document workflow service for the Mortgage Intelligence Platform",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "mortgage-analytics-service"}