from fastapi import FastAPI

from app.api.routes import router


app = FastAPI(
    title="Agent Squad API",
    description=(
        "Multi-agent software development workflow powered by CrewAI "
        "and Gemini."
    ),
    version="1.0.0",
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "message": "Agent Squad API is running.",
        "docs": "/docs",
        "workflow_endpoint": "/api/run",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
