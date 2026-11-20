from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.flows.development_flow import DevelopmentFlow
from app.services.jobs import (
    RepositoryBusyError,
    acquire_repository,
    build_result,
    create_job,
    execute_job,
    job_store,
    release_repository,
)
from app.workspace import repository_exists


router = APIRouter(prefix="/api", tags=["Agent Squad"])

ERROR_STATUS_CODES = {
    "QUOTA_EXCEEDED": 503,
    "REPOSITORY_NOT_FOUND": 404,
}


class DevelopmentRequest(BaseModel):
    repository_name: str = Field(
        ...,
        min_length=1,
        description="Repository folder name inside workspace/repositories.",
    )
    user_request: str = Field(
        ...,
        min_length=5,
        description="Feature request or software change to implement.",
    )


def _validated_repository(request: DevelopmentRequest) -> str:
    name = request.repository_name.strip()

    if not repository_exists(name):
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{name}' was not found in "
            "workspace/repositories.",
        )

    return name


def _busy(name: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=f"Repository '{name}' already has a run in progress.",
    )


@router.post("/run")
def run_development(request: DevelopmentRequest):
    """Run the workflow and wait for it to finish (can take minutes)."""

    name = _validated_repository(request)

    try:
        acquire_repository(name)
    except RepositoryBusyError:
        raise _busy(name)

    try:
        flow = DevelopmentFlow()

        flow.kickoff(
            inputs={
                "repository_name": name,
                "user_request": request.user_request.strip(),
            }
        )
    finally:
        release_repository(name)

    if flow.state.status == "failed":
        raise HTTPException(
            status_code=ERROR_STATUS_CODES.get(flow.state.error_code, 500),
            detail={
                "status": "failed",
                "error_code": flow.state.error_code,
                "error": flow.state.error,
                "report": flow.state.final_report,
            },
        )

    return build_result(flow)


@router.post("/jobs", status_code=202)
def start_job(request: DevelopmentRequest, background_tasks: BackgroundTasks):
    """Start the workflow in the background and return a job id at once."""

    name = _validated_repository(request)

    try:
        job = create_job(name, request.user_request.strip())
    except RepositoryBusyError:
        raise _busy(name)

    background_tasks.add_task(execute_job, job)

    return {
        "job_id": job.id,
        "status": "queued",
        "status_url": f"/api/jobs/{job.id}",
    }


@router.get("/jobs")
def list_jobs(limit: int = 20):
    """Most recent jobs, newest first (summary only, without reports)."""

    summaries = []

    for job in job_store.recent(max(1, min(limit, 100))):
        data = job.snapshot()
        data.pop("result", None)
        summaries.append(data)

    return summaries


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Live stage while running; full result once finished."""

    job = job_store.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job.snapshot()
