import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


# Environment variables whose names contain these markers are NOT passed to
# the pytest subprocess. Pytest executes code from the target repository (which
# an LLM may just have written), so it must not be able to read API keys.
SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def sanitized_environment() -> dict:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS)
    }
    # Keep the repository clean: no __pycache__ noise in Git diffs.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


@dataclass
class PytestResult:
    status: str  # PASSED | FAILED | TIMEOUT | NOT RUN
    exit_code: Optional[int]
    command: str
    output: str

    def format(self) -> str:
        lines = [f"TEST STATUS: {self.status}"]
        if self.exit_code is not None:
            lines.append(f"EXIT CODE: {self.exit_code}")
        lines.append(f"COMMAND: {self.command}")
        lines.append("")
        lines.append(self.output)
        return "\n".join(lines)


def resolve_test_target(repository_path: Path, test_path: Optional[str]) -> str:
    """Pick the test path: the explicit one, else tests/ if present, else '.'."""

    if test_path:
        return test_path
    return "tests" if (repository_path / "tests").is_dir() else "."


def run_pytest(
    repository_name: str,
    test_path: Optional[str] = None,
    timeout_seconds: int = 120,
) -> PytestResult:
    """Run pytest inside a workspace repository and return the real result.

    This is the single source of truth for test status. It is used both by
    the Tester agent's tool and directly by the workflow, so the final
    status never depends on an LLM repeating tool output correctly.
    """

    repository_path = (WORKSPACE_ROOT / repository_name).resolve()

    if not repository_path.is_relative_to(WORKSPACE_ROOT):
        return PytestResult("NOT RUN", None, "-", "ERROR: Repository path is outside the workspace.")
    if repository_path == WORKSPACE_ROOT or not repository_path.is_dir():
        return PytestResult("NOT RUN", None, "-", "ERROR: Repository does not exist.")

    target = (repository_path / resolve_test_target(repository_path, test_path)).resolve()

    if not target.is_relative_to(repository_path):
        return PytestResult("NOT RUN", None, "-", "ERROR: Test path escapes the repository.")
    if not target.exists():
        return PytestResult("NOT RUN", None, "-", f"ERROR: Test path does not exist: {test_path}")

    relative_target = target.relative_to(repository_path)
    shown_target = str(relative_target)
    command = [
        sys.executable,
        "-m",
        "pytest",
        shown_target,
        "-q",
        "--disable-warnings",
        "-p",
        "no:cacheprovider",
    ]
    display_command = f"python -m pytest {shown_target} -q"

    try:
        completed = subprocess.run(
            command,
            cwd=str(repository_path),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=sanitized_environment(),
        )
    except subprocess.TimeoutExpired:
        return PytestResult(
            "TIMEOUT",
            None,
            display_command,
            f"Pytest exceeded the {timeout_seconds}-second time limit.",
        )
    except Exception as error:
        return PytestResult(
            "NOT RUN",
            None,
            display_command,
            f"TEST EXECUTION ERROR: {type(error).__name__}: {error}",
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    output = (stdout + ("\nSTDERR:\n" + stderr if stderr else "")).strip()
    if len(output) > 12000:
        output = output[:12000] + "\n... output truncated ..."
    output = output or "Pytest returned no output."

    if completed.returncode == 0:
        status = "PASSED"
    elif completed.returncode == 5:
        # pytest exit code 5 = no tests were collected. Nothing failed, but
        # nothing was verified either, so it must not trigger a "fix" loop.
        status = "NOT RUN"
        output = "No tests were collected.\n\n" + output
    elif "No module named pytest" in stderr:
        status = "NOT RUN"
        output = "pytest is not installed in this environment.\n\n" + output
    else:
        status = "FAILED"

    return PytestResult(status, completed.returncode, display_command, output)


class TestRunnerInput(BaseModel):
    repository_name: str = Field(
        ...,
        description="Repository name inside workspace/repositories.",
    )
    test_path: str = Field(
        default="tests",
        description=(
            "Relative test file or directory. Defaults to tests; if that "
            "directory does not exist, the whole repository is searched."
        ),
    )
    timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=300,
        description="Maximum test execution time, between 1 and 300 seconds.",
    )


class TestRunnerTool(BaseTool):
    name: str = "Repository Pytest Runner"
    description: str = (
        "Execute pytest for a test file or test directory inside the selected "
        "workspace repository. Returns the real exit code and captured output. "
        "Only pytest is supported; arbitrary shell commands cannot be run."
    )
    args_schema: type[BaseModel] = TestRunnerInput

    def _run(
        self,
        repository_name: str,
        test_path: str = "tests",
        timeout_seconds: int = 120,
    ) -> str:
        repository_path = (WORKSPACE_ROOT / repository_name).resolve()

        # The default "tests" falls back to auto-discovery, so the agent does
        # not waste iterations on repositories whose tests live in the root.
        if (
            test_path == "tests"
            and repository_path.is_dir()
            and not (repository_path / "tests").exists()
        ):
            test_path = None

        return run_pytest(repository_name, test_path, timeout_seconds).format()
