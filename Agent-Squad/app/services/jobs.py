"""Background jobs and per-repository locking for the Agent Squad API.

Jobs are kept in memory: they are lost when the server restarts, and the
store only remembers the most recent MAX_JOBS runs.
"""

import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from app.flows.development_flow import DevelopmentFlow
from app.tools.repository_tools import WORKSPACE_ROOT


MAX_JOBS = 100


class RepositoryBusyError(Exception):
    """Another run is already modifying this repository."""


_active_repositories: set[str] = set()
_active_lock = threading.Lock()


def _repository_key(repository_name: str) -> str:
    return str((WORKSPACE_ROOT / repository_name).resolve())


def acquire_repository(repository_name: str) -> None:
    """Reserve a repository. Two runs editing one repo would corrupt it."""

    key = _repository_key(repository_name)

    with _active_lock:
        if key in _active_repositories:
            raise RepositoryBusyError(repository_name)
        _active_repositories.add(key)


def release_repository(repository_name: str) -> None:
    with _active_lock:
        _active_repositories.discard(_repository_key(repository_name))


def build_result(flow: DevelopmentFlow) -> dict:
    """The response payload shared by the sync endpoint and job results."""

    state = flow.state

    return {
        "status": state.status,
        "repository": state.repository_name,
        "report": state.final_report,
        "review_verdict": state.review_verdict,
        "testing": {
            "status": state.test_status,
            "correction_attempts": state.correction_attempts,
            "history": list(state.test_history),
        },
        "warnings": list(state.warnings),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Job:
    def __init__(self, repository_name: str, user_request: str):
        self.id = uuid.uuid4().hex
        self.repository_name = repository_name
        self.user_request = user_request
        self.created_at = _now()
        self.finished_at: Optional[str] = None
        self.flow: Optional[DevelopmentFlow] = None
        self.crash: str = ""

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    def snapshot(self) -> dict:
        flow = self.flow

        if self.crash:
            status, stage = "failed", "failed"
            error, error_code = self.crash, "UNEXPECTED_ERROR"
        elif flow is None:
            status, stage, error, error_code = "queued", "queued", "", ""
        else:
            status = flow.state.status
            stage = flow.state.stage
            error = flow.state.error
            error_code = flow.state.error_code

        data = {
            "job_id": self.id,
            "repository": self.repository_name,
            "status": status,
            "stage": stage,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": error,
            "error_code": error_code,
        }

        if flow is not None:
            data["progress"] = {
                "correction_attempts": flow.state.correction_attempts,
                "test_history": list(flow.state.test_history),
            }

        if self.finished and flow is not None:
            data["result"] = build_result(flow)

        return data


class JobStore:
    def __init__(self) -> None:
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()

    def add(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

            # Evict the oldest finished jobs; never drop a running one.
            while len(self._jobs) > MAX_JOBS:
                oldest_finished = next(
                    (key for key, item in self._jobs.items() if item.finished),
                    None,
                )
                if oldest_finished is None:
                    break
                del self._jobs[oldest_finished]

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            return list(reversed(self._jobs.values()))[:limit]


job_store = JobStore()


def create_job(repository_name: str, user_request: str) -> Job:
    """Reserve the repository and register a queued job.

    Raises RepositoryBusyError if the repository is already in use.
    """

    acquire_repository(repository_name)

    job = Job(repository_name, user_request)
    job_store.add(job)

    return job


def execute_job(job: Job) -> None:
    """Run the workflow for a job created by create_job (background thread)."""

    try:
        flow = DevelopmentFlow()
        job.flow = flow

        flow.kickoff(
            inputs={
                "repository_name": job.repository_name,
                "user_request": job.user_request,
            }
        )
    except Exception as error:
        job.crash = f"{type(error).__name__} : {error}"
    finally:
        job.finished_at = _now()
        release_repository(job.repository_name)
