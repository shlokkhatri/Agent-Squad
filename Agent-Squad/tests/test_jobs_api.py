import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.flows.development_flow import DevelopmentState
from app.main import app
from app.services import jobs

client = TestClient(app)


class FakeFlow:
    """Stands in for DevelopmentFlow; behaviour is set per test."""

    outcome = {"status": "completed", "test_status": "PASSED"}

    def __init__(self):
        self.state = DevelopmentState()

    def kickoff(self, inputs):
        self.state.repository_name = inputs["repository_name"]
        self.state.user_request = inputs["user_request"]
        self.state.stage = "done"
        self.state.final_report = "REPORT"
        for key, value in self.outcome.items():
            setattr(self.state, key, value)
        if self.state.test_status == "PASSED":
            self.state.test_history.append("PASSED")


@pytest.fixture(autouse=True)
def fake_flow(monkeypatch):
    monkeypatch.setattr(jobs, "DevelopmentFlow", FakeFlow)
    monkeypatch.setattr(routes, "DevelopmentFlow", FakeFlow)
    FakeFlow.outcome = {"status": "completed", "test_status": "PASSED"}


BODY = {"repository_name": "sample_project", "user_request": "add a health endpoint"}


def test_unknown_repository_is_404():
    for path in ("/api/run", "/api/jobs"):
        response = client.post(path, json={**BODY, "repository_name": "nope"})
        assert response.status_code == 404


def test_path_traversal_name_is_404():
    response = client.post("/api/jobs", json={**BODY, "repository_name": ".."})

    assert response.status_code == 404


def test_job_lifecycle():
    response = client.post("/api/jobs", json=BODY)

    assert response.status_code == 202
    started = response.json()
    assert started["status"] == "queued"
    assert started["status_url"] == f"/api/jobs/{started['job_id']}"

    # TestClient runs background tasks before returning, so it is finished.
    job = client.get(started["status_url"]).json()

    assert job["status"] == "completed"
    assert job["finished_at"] is not None
    assert job["result"]["report"] == "REPORT"
    assert job["result"]["testing"]["status"] == "PASSED"

    listed = client.get("/api/jobs").json()
    assert any(item["job_id"] == started["job_id"] for item in listed)
    assert all("result" not in item for item in listed)


def test_unknown_job_is_404():
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_busy_repository_returns_409_and_is_released_afterwards():
    jobs.acquire_repository("sample_project")
    try:
        assert client.post("/api/jobs", json=BODY).status_code == 409
        assert client.post("/api/run", json=BODY).status_code == 409
    finally:
        jobs.release_repository("sample_project")

    assert client.post("/api/jobs", json=BODY).status_code == 202
    # Finished jobs free the repository again.
    assert client.post("/api/run", json=BODY).status_code == 200


def test_sync_run_keeps_its_response_shape():
    data = client.post("/api/run", json=BODY).json()

    assert data["status"] == "completed"
    assert data["repository"] == "sample_project"
    assert set(data["testing"]) == {"status", "correction_attempts", "history"}


def test_quota_failure_is_503_not_500():
    """The old check compared against 'GEMINI_QUOTA_EXCEEDED', which the
    error text never contained, so the API always answered 500."""

    FakeFlow.outcome = {
        "status": "failed",
        "error_code": "QUOTA_EXCEEDED",
        "error": "quota",
    }

    assert client.post("/api/run", json=BODY).status_code == 503

    job = client.post("/api/jobs", json=BODY).json()
    snapshot = client.get(job["status_url"]).json()
    assert snapshot["status"] == "failed"
    assert snapshot["error_code"] == "QUOTA_EXCEEDED"


def test_crash_inside_a_job_is_captured_and_repository_released(monkeypatch):
    class CrashingFlow(FakeFlow):
        def kickoff(self, inputs):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(jobs, "DevelopmentFlow", CrashingFlow)

    started = client.post("/api/jobs", json=BODY).json()
    snapshot = client.get(started["status_url"]).json()

    assert snapshot["status"] == "failed"
    assert "kaboom" in snapshot["error"]
    assert client.post("/api/jobs", json=BODY).status_code == 202
