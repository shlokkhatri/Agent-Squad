from types import SimpleNamespace

import pytest

from app.flows import development_flow
from app.flows.development_flow import DevelopmentFlow


def output(*texts):
    return SimpleNamespace(
        tasks_output=[SimpleNamespace(raw=text) for text in texts],
        raw=texts[-1],
    )


# ---------- pure helpers ----------

def test_status_uses_last_marker_not_first():
    text = "previous run: TEST STATUS: FAILED\n...\nTEST STATUS: PASSED\nEXIT CODE: 0"

    assert DevelopmentFlow.extract_test_status(text) == "PASSED"


def test_status_unknown_without_marker():
    assert DevelopmentFlow.extract_test_status("no marker here") == "UNKNOWN"


def test_task_output_reads_every_task():
    """CrewAI's attribute is `tasks_output`; the old code looked for `task_output`."""

    text = DevelopmentFlow.extract_task_output(output("PLAN", "CODE", "TESTS"))

    assert "PLAN" in text and "CODE" in text and "TESTS" in text
    assert "Task 1" in text and "Task 3" in text


@pytest.mark.parametrize(
    "message, expected",
    [
        ("429 RESOURCE_EXHAUSTED: quota exceeded", True),
        ("HTTP error 429 Too Many Requests", True),
        ("GenerateRequestsPerDayPerProjectPerModel limit hit", True),
        ("Something failed at line 429 of main.py", False),
        ("KeyError: 'name'", False),
    ],
)
def test_quota_detection(message, expected):
    assert DevelopmentFlow.is_quota_error(Exception(message)) is expected


def test_quota_detection_by_exception_type():
    class RateLimitError(Exception):
        pass

    assert DevelopmentFlow.is_quota_error(RateLimitError("boom")) is True


@pytest.mark.parametrize(
    "review_text, expected",
    [
        ("Result: APPROVED. No blockers.", "APPROVED"),
        ("CHANGES REQUIRED: missing validation", "CHANGES REQUIRED"),
        ("This is not APPROVED. Changes required.", "CHANGES REQUIRED"),
        ("looks fine to me", "UNKNOWN"),
    ],
)
def test_review_verdict(review_text, expected):
    result = output("a", "b", "c", "d", "e", review_text, "tests")

    assert DevelopmentFlow.extract_review_verdict(result) == expected


# ---------- whole flow with fake crews (no LLM calls) ----------

class FakeCrew:
    def __init__(self, result, side_effect=None):
        self._result = result
        self._side_effect = side_effect

    def kickoff(self, inputs):
        if self._side_effect:
            self._side_effect(inputs)
        return self._result


def fake_crew_factory(initial_result, correction_result, on_correction=None, on_initial=None):
    calls = {"initial": 0, "correction": 0, "feedback": []}

    class FakeDevelopmentCrew:
        def initial_crew(self):
            calls["initial"] += 1
            return FakeCrew(initial_result, on_initial)

        def correction_crew(self):
            calls["correction"] += 1

            def side_effect(inputs):
                calls["feedback"].append(inputs["test_feedback"])
                if on_correction:
                    on_correction(inputs)

            return FakeCrew(correction_result, side_effect)

    return FakeDevelopmentCrew, calls


def initial_result(tester_claim, verdict="APPROVED"):
    return output(
        "brief", "plan", "implementation", "review", "revision",
        verdict, f"TEST STATUS: {tester_claim}",
    )


def run_flow(monkeypatch, repo_name, crew_class):
    monkeypatch.setattr(development_flow, "DevelopmentCrew", crew_class)
    flow = DevelopmentFlow()
    flow.kickoff(inputs={"repository_name": repo_name, "user_request": "do the thing"})
    return flow


def test_flow_corrects_a_failure_the_tester_agent_claimed_was_fine(monkeypatch, temp_repo):
    """The Tester LLM says PASSED, but the real test fails. The flow must
    notice, send REAL pytest output to the coder, and finish on the real result."""

    name, path = temp_repo
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (path / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )

    def coder_fixes_bug(inputs):
        (path / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    crews, calls = fake_crew_factory(
        initial_result("PASSED"),  # a wrong claim
        output("root cause: wrong operator", "correction review ok"),
        on_correction=coder_fixes_bug,
    )

    flow = run_flow(monkeypatch, name, crews)

    assert flow.state.status == "completed"
    assert flow.state.test_status == "PASSED"
    assert flow.state.test_history == ["FAILED", "PASSED"]
    assert flow.state.correction_attempts == 1
    assert any("Tester agent reported PASSED" in w for w in flow.state.warnings)

    # The coder got real pytest output, not an LLM summary.
    assert "assert -1 == 5" in calls["feedback"][0] or "assert" in calls["feedback"][0]
    assert "TEST STATUS: FAILED" in calls["feedback"][0]

    # The report contains every stage, not just the last task.
    assert "implementation" in flow.state.final_report
    assert "FINAL TEST STATUS (verified by direct pytest run): PASSED" in flow.state.final_report

    # Reviewers had a baseline to diff against.
    assert (path / ".git").is_dir()


def test_flow_stops_after_max_retries(monkeypatch, temp_repo):
    name, path = temp_repo
    (path / "test_always_fails.py").write_text("def test_x():\n    assert False\n")

    crews, calls = fake_crew_factory(
        initial_result("FAILED"), output("tried", "reviewed")
    )

    flow = run_flow(monkeypatch, name, crews)

    assert calls["correction"] == development_flow.MAX_CORRECTION_RETRIES
    assert flow.state.status == "completed_with_test_failures"
    assert flow.state.test_history == ["FAILED"] * 3


def test_no_tests_does_not_trigger_corrections(monkeypatch, temp_repo):
    name, path = temp_repo
    (path / "main.py").write_text("x = 1\n")

    crews, calls = fake_crew_factory(initial_result("PASSED"), output("n/a"))

    flow = run_flow(monkeypatch, name, crews)

    assert calls["correction"] == 0
    assert flow.state.test_status == "NOT RUN"
    assert flow.state.status == "completed_with_unverified_tests"


def test_open_review_findings_are_not_reported_as_clean_success(monkeypatch, temp_repo):
    name, path = temp_repo
    (path / "test_ok.py").write_text("def test_ok():\n    assert True\n")

    crews, _ = fake_crew_factory(
        initial_result("PASSED", verdict="CHANGES REQUIRED: SQL injection"),
        output("x"),
    )

    flow = run_flow(monkeypatch, name, crews)

    assert flow.state.test_status == "PASSED"
    assert flow.state.review_verdict == "CHANGES REQUIRED"
    assert flow.state.status == "completed_with_open_review_findings"


def test_unknown_repository_fails_before_any_llm_call(monkeypatch):
    crews, calls = fake_crew_factory(initial_result("PASSED"), output("x"))

    flow = run_flow(monkeypatch, "no_such_repository", crews)

    assert flow.state.status == "failed"
    assert flow.state.error_code == "REPOSITORY_NOT_FOUND"
    assert calls["initial"] == 0


def test_quota_error_sets_error_code(monkeypatch, temp_repo):
    name, _ = temp_repo

    class ExplodingCrew:
        def initial_crew(self):
            raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

    flow = run_flow(monkeypatch, name, ExplodingCrew)

    assert flow.state.status == "failed"
    assert flow.state.error_code == "QUOTA_EXCEEDED"
