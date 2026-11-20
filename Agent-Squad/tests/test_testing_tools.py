import os

from app.tools.testing_tools import run_pytest


def write(path, name, text):
    (path / name).write_text(text, encoding="utf-8")


def test_passing_tests_report_passed(temp_repo):
    name, path = temp_repo
    write(path, "test_ok.py", "def test_ok():\n    assert 1 + 1 == 2\n")

    result = run_pytest(name)

    assert result.status == "PASSED"
    assert result.exit_code == 0
    assert "TEST STATUS: PASSED" in result.format()


def test_failing_tests_report_failed(temp_repo):
    name, path = temp_repo
    write(path, "test_bad.py", "def test_bad():\n    assert False\n")

    assert run_pytest(name).status == "FAILED"


def test_no_tests_is_not_run_not_failed(temp_repo):
    """Exit code 5 must not start a pointless 'fix the failing tests' loop."""

    name, path = temp_repo
    write(path, "app.py", "x = 1\n")

    result = run_pytest(name)

    assert result.status == "NOT RUN"
    assert "No tests were collected" in result.output


def test_timeout_is_reported(temp_repo):
    name, path = temp_repo
    write(path, "test_slow.py", "import time\n\ndef test_slow():\n    time.sleep(30)\n")

    assert run_pytest(name, timeout_seconds=1).status == "TIMEOUT"


def test_secrets_are_not_visible_to_repository_code(temp_repo, monkeypatch):
    name, path = temp_repo
    monkeypatch.setenv("SOME_SERVICE_API_KEY", "super-secret-value")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    write(
        path,
        "test_env.py",
        "import os\n\n"
        "def test_no_secrets():\n"
        "    assert 'SOME_SERVICE_API_KEY' not in os.environ\n"
        "    assert 'GITHUB_TOKEN' not in os.environ\n"
        "    assert 'GEMINI_API_KEY' not in os.environ\n",
    )

    assert run_pytest(name).status == "PASSED"


def test_unknown_repository_is_not_run():
    assert run_pytest("does_not_exist_anywhere").status == "NOT RUN"


def test_path_escape_is_rejected(temp_repo):
    name, _ = temp_repo

    assert run_pytest(name, test_path="../..").status == "NOT RUN"
