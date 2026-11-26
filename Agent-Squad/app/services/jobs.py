"""Background jobs and pre-repository locking for Agent Squad. """

import threading
import uuid

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from app.flows.development_flow import DevelopmentFlow
from app.tools.repository_tools import WORKSPACE_ROOT

from app.integrations.github_service import (
    GithubIntegrationError,
    clone_repository,
    create_development_branch,
    commit_changes,
    push_development_branch,
    create_pull_request,
)


MAX_JOBS = 100

_active_repositories = set()
_active_lock = threading.Lock()

class RepositoryBusyError(Exception):
    """Another run is modified repository."""

def _repository_key(repository_name):
    return str(
        (WORKSPACE_ROOT/repository_name).resolve()
    )

def acquire_repository(repository_name):
    key = _repository_key(repository_name)

    with _active_lock:
        if key in _active_repositories:
            raise RepositoryBusyError(repository_name)

        _active_repositories.add(key)


def release_repository(repository_name):
    with _active_lock:
        _active_repositories.discard(
            _repository_key(repository_name)
        )


def build_result(flow):
    state = flow.state

    return{
        "status" : state.status,
        "repository" : state.repository_name,
        "report" : state.final_report,
        "review_verdict" :state.review_verdict,
        "testing" : {
            "status" : state.test_status,
            "correction_attempts" : state.correction_attempts,
            "history" :list(state.test_history),
        },
        "warnings" : list(state.warnings)
    }


def _now() :
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


class Job:

    def __init__(
        self,
        repository_name,
        user_request,
        source,
        repository_url,
        base_branch,
    ):
        self.id = uuid.uuid4().hex

        self.repository_name = repository_name
        self.user_request = user_request

        self.source = source
        self.repository_url = repository_url
        self.base_branch = base_branch

        self.development_branch: Optional[str] = None

        self.flow: Optional[DevelopmentFlow] = None
        self.crash: str = ""

        self.status = "queued"
        self.stage = "queued"

        self.created_at = _now()
        self.finished_at = None

        self.publishing: dict = {
            "status": "not_started"
        }

    @property
    def finished(self):
        return self.finished_at is not None

    def snapshot(self) :
        flow = self.flow

        if self.crash:
            status = "failed"
            stage = "failed"
            error = self.crash
            error_code = "UNEXPECTED_ERROR"

        elif flow is None:
            status = self.status
            stage = self.stage
            error = ""
            error_code = ""

        else:
            status = flow.state.status

            if self.stage in {
                "commiting",
                "pushing",
                "commiting_pull_request"
            }:
                stage = self.stage

            else :
                stage = flow.state.stage

            error = flow.state.error
            error_code = flow.state.error_code

        data = {
            "job_id": self.id,
            "repository": self.repository_name,
            "source": self.source,
            "repository_url": self.repository_url,
            "base_branch": self.base_branch,
            "development_branch": self.development_branch,
            "status": status,
            "stage": stage,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": error,
            "error_code": error_code,
            "publishing": self.publishing,
        }

        if flow is not None:
            data["process"] = {
                "correction_attempts" : (
                    flow.state.correction_attempts
                ),
                "test_history" : list(
                    flow.state.test_history
                ),
            }


        if self.finished and flow is not None:
            result = build_result(flow)
            result["publishing"] = self.publishing
            result["repository_url"] = self.repository_url
            result["base_branch"] = self.base_branch
            result["development_branch"] = self.development_branch
            data["result"] = result

        return data

class JobStore:

    def __init__(self):
        self._jobs = OrderedDict()
        self._lock = threading.Lock()

    def add(self, job) :
        
        with self._lock:
            self._jobs[job.id] = job

            while len(self._jobs) > MAX_JOBS:
                oldest_finished = next(
                (
                        key
                        for key, item in self._jobs.items()
                        if item.finished
                    ),
                    None,
                )

                if oldest_finished is None:
                    break

                del self._jobs[oldest_finished]


    def get(self, job_id) :

        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit) :
        with self._lock:
            return list(
                reversed(self._jobs.values())
            )[:limit]

job_store = JobStore()

def create_job(
    repository_name,
    user_request,
    source,
    repository_url,
    base_branch
):

    acquire_repository(repository_name)

    try:
        job = Job(
            repository_name=repository_name,
            user_request=user_request,
            source=source,
            repository_url=repository_url,
            base_branch=base_branch
        )

        job_store.add(job)

        return job

    except Exception:
        release_repository(repository_name)
        raise


def _publish_github_changes(job:Job):
    """Publish changes only after test and reviews are approved."""

    state = job.flow.state

    if not state.can_publish:
        job.publishing = {
            "status" : "skipped",
            "reason" : (
                "Publishing requires complete development, "
                "passing tests, and an APPROVED final code review. "
            ),
        }

        return

    job.stage = "committing"

    commit_result = commit_changes(
        repository_name=job.repository_name,
        commit_message="Agent Squad: Implement requested changes"
    )

    if commit_result["status"] == "no_changes":

        job.publishing = {
            "status" : "skipped",
            "reason" : "No changes were available to publish."
        }

        return

    job.stage = "pushing"

    push_result = push_development_branch(
        repository_name=job.repository_name,
        branch_name=job.development_branch,
    )

    job.stage = "creating_pull_request"

    pr_result = create_pull_request(
        repository_url=job.repository_url,
        base_branch=job.base_branch,
        development_branch=job.development_branch,
        title=f"Agent Squad: {job.user_request[:70]}",
        body= (
            "## Summary\n\n"
            f"{job.user_request}\n\n"
            "## Automated Verification\n\n"
            f"- Tests: {state.test_status}\n"
            f"- Code review: {state.review_verdict}\n"
            f"- Correction attempts: {state.correction_attempts}\n\n"
            "Created automatically by Agent Squad."
        ),
    )


    job.publishing = {
        "status" : "completed",
        "commit" : commit_result["commit"],
        "push" : push_result,
        "pull_request" : pr_result
    }


def execute_job(job:Job):
    """Execute cloning, development, verification and publishing."""

    try:
    
        # clone GitHub repository

        if job.source == "github":

            job.status = "running"
            job.stage = "cloning"

            repository = clone_repository(
                repository_url = job.repository_url,
                base_branch = job.base_branch,
            )

            job.repository_name = repository["repository_name"]
            job.base_branch = repository["base_branch"]



            # Create Development branch

            job.stage = "creating_branch"

            branch_name = (
                "agent_squad/"
                + datetime.now(timezone.utc).strftime(
                    "%Y%m%d-%H%M%S"
                )
                + "-"
                + uuid.uuid4().hex[:6]
            )

            job.development_branch = (
                create_development_branch(
                    repository_name=job.repository_name,
                    branch_name=branch_name,
                )
            )



        # Run existing CrewAI workflow

        job.status = "running"
        job.stage = "development"

        flow = DevelopmentFlow()
        job.flow = flow

        flow.kickoff(
            inputs = {
                "repository_name": job.repository_name,
                    "user_request": job.user_request,
            }
        )



        # GitHub publishing

        if job.source == "github":

            if flow.state.status == "failed":

                job.publishing = {
                    "status": "skipped",
                    "reason": "Development workflow failed.",
                }

            else:

                try:
                    _publish_github_changes(job)

                except Exception as error:
                    job.publishing = {
                        "status": "failed",
                        "error": (
                            f"{type(error).__name__}: {error}"
                        ),
                    }

        # Final job status — applies to GitHub and local jobs.

        job.status = flow.state.status

        if flow.state.status == "completed":
            job.stage = "completed"
        else:
            job.stage = "failed"

    except Exception as error :

        job.crash = (
            f"{type(error).__name__}: {error}"
        )

        job.status = "failed"
        job.stage = "failed"

    finally:

        job.finished_at = _now()

        release_repository(job.repository_name)