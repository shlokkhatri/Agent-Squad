import uuid

from datetime import datetime, timezone

from fastapi import APIRouter,BackgroundTasks,HTTPException
from pydantic import BaseModel,Field

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

from app.integrations.github_service import (
    GithubIntegrationError,
    clone_repository,
    create_development_branch,
    validate_github_url,
    repository_directory_name,
)

router = APIRouter(
    prefix="/api",
    tags= ["Agent Squad"]
)

ERROR_STATUS_CODE = {
    "QUOTA_EXCEEDED" : 503,
    "REPOSITORY_NOT_FOUND" : 404,
}



class DevelopmentRequest(BaseModel):

    repository_name: str | None = Field(default=None)

    repository_url: str | None = Field(default=None)

    base_branch: str | None = Field(
        default=None,
        description=(
            "Optional GitHub base branch. "
            "If omitted, Agent Squad detects the default branch."
        ),
    )

    user_request: str = Field(
        ...,
        min_length=5,
    )

def _resolve_repository(request):

    if bool(request.repository_name) == bool(
        request.repository_url
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide exactly one of repository_name "
                "or repository_url"
            ),
        )

    if request.repository_name:

        name =request.repository_name.strip()

        if not repository_exists(name):

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Repository '{name}' was not found "
                    "inside workspace/repositories."
                )
            )

        return {
            "repository_name" : name,
            "source" : "local",
            "repository_url" : None,
            "branch" : None,
            "base_branch" : None
        }

    try :

        repository = clone_repository(
            repository_url=request.repository_url,
            base_branch=request.base_branch
        )

        branch_name = (
            "agent_squad/"
            + datetime.now(timezone.utc).strftime(
                "%Y%m%d-%H%M%S"
            )
            + "-"
            + uuid.uuid4().hex[:6]
        )

        create_development_branch(
            repository_name=repository["repository_name"],
            branch_name=branch_name,
        )

        return {
            "repository_name": repository["repository_name"],
            "source": "github",
            "repository_url": repository["repository_url"],
            "branch": branch_name,
            "base_branch": repository["base_branch"],
        }

    except GithubIntegrationError as error:

        raise HTTPException(
            status_code= 400,
            detail=str(error)
        )


def _busy(name) :
    return HTTPException(
        status_code= 409,
        detail= (
            f"Repository '{name}' already has "
            "a development run in progress."
        ),
    )

@router.post("/run")
def run_development(request: DevelopmentRequest):

    repository = _resolve_repository(request)

    name = repository["repository_name"]

    try :
        acquire_repository(name)

    except RepositoryBusyError:
        raise _busy(name)

    try :

        flow = DevelopmentFlow()

        flow.kickoff(
            inputs = {
                "repository_name" : name,
                "user_request" : request.user_request.strip()
            }
        )

    finally :
        release_repository(name)

    if flow.state.status == "failed" :

        raise HTTPException(
            status_code= ERROR_STATUS_CODE.get(
                flow.state.error_code,
                500,
            ),
            detail={
                "status" : "failed",
                "error_code" : flow.state.error_code,
                "error" : flow.state.error,
                "report" : flow.state.final_report
            }
        )

    result = build_result(flow)

    result["source"] = repository["source"]
    result["repository_url"] = repository["repository_url"]
    result["branch"] = repository["branch"]
    result["base_branch"] = repository["base_branch"]

    return result


@router.post("/jobs", status_code=202)
def start_job(
    request: DevelopmentRequest,
    background_task: BackgroundTasks,
):
    """Start the complete workflow in background."""

    if bool(request.repository_name) == bool(request.repository_url):

        raise HTTPException(
            status_code=400,
            detail=(
                "Provide exactly one of repository_name "
                "or repository_url."
            ),
        )
    
    try :

        if request.repository_name:

            name = request.repository_name.strip()

            if not repository_exists(name):

                raise HTTPException(
                    status_code= 404,
                    detail=f"Repository '{name}' was not found."
                )
            source = "local"
            repository_url = None
            base_branch = None


        else :

            owner, repository = validate_github_url(
                request.repository_url
            )

            name = repository_directory_name(
                owner,
                repository
            )

            source = "github"
            repository_url = request.repository_url.strip()

            base_branch = (
                request.base_branch.strip()
                if request.base_branch
                else None
            )

        job = create_job(
            repository_name= name,
            user_request= request.user_request.strip(),
            source = source,
            repository_url= repository_url,
            base_branch= base_branch,
        )

    except RepositoryBusyError:

        raise _busy(name)

    except GithubIntegrationError as error:

        raise HTTPException(
            status_code= 400,
            detail= str(error)
        )

    background_task.add_task(
        execute_job,
        job
    )

    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "repository": job.repository_name,
        "source": job.source,
        "repository_url": job.repository_url,
        "base_branch": job.base_branch,
        "development_branch": job.development_branch,
        "status_url": f"/api/jobs/{job.id}",
    }

@router.get("/jobs")
def list_jobs(limit: int = 20):

    summaries = []

    for job in job_store.recent(
        max(1,min(limit, 100))
    ):

        data = job.snapshot()
        data.pop("result", None)

        summaries.append(data)

    return summaries


@router.get("/jobs/{job_id}")
def get_job(job_id: str):

    job = job_store.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found."
        )

    return job.snapshot()