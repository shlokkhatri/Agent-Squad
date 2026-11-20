import subprocess
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


class GitRepositoryInput(BaseModel):
    repository_name: str = Field(
        ...,
        description="Repository name inside workspace/repositories.",
    )


def _repository_path(repository_name: str) -> Path:
    path = (WORKSPACE_ROOT / repository_name).resolve()
    if not path.is_relative_to(WORKSPACE_ROOT) or path == WORKSPACE_ROOT:
        raise ValueError("Repository path is outside the allowed workspace.")
    if not path.is_dir():
        raise ValueError("Repository does not exist.")
    return path


def _run_git(repository_path: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(repository_path),
        capture_output=True,
        text=True,
        timeout=20,
        shell=False,
    )
    if result.returncode != 0:
        return (result.stderr or result.stdout or "Git command failed.").strip()
    return (result.stdout or "No output.").strip()


def _git(repository_path: Path, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=str(repository_path),
        capture_output=True,
        text=True,
        timeout=20,
        shell=False,
    )


# Patterns kept out of Git's view via .git/info/exclude (local to the clone),
# so the baseline never adds files to the user's working tree.
_LOCAL_EXCLUDES = ["__pycache__/", "*.pyc", ".pytest_cache/", ".venv/", "venv/"]


def ensure_git_baseline(repository_name: str) -> str:
    """Give a repository its own Git history so reviewers can see diffs.

    Without this, `git diff` fails in a plain folder (or worse, reports the
    diff of some parent repository). Returns "existing" when the repository
    already has Git metadata and was left untouched, or "initialized" after
    creating a baseline commit of the current state.
    """

    repository_path = _repository_path(repository_name)

    if (repository_path / ".git").exists():
        return "existing"

    steps = [
        ["init"],
        ["add", "-A"],
        [
            "-c", "user.name=Agent Squad",
            "-c", "user.email=agent-squad@localhost",
            "-c", "commit.gpgsign=false",
            "commit", "--allow-empty", "-m", "Agent Squad baseline",
        ],
    ]

    for index, arguments in enumerate(steps):
        completed = _git(repository_path, arguments)
        if completed.returncode != 0:
            raise RuntimeError(
                f"git {arguments[-1] if arguments[0] == '-c' else arguments[0]} "
                f"failed: {(completed.stderr or completed.stdout).strip()}"
            )
        if index == 0:
            exclude_file = repository_path / ".git" / "info" / "exclude"
            exclude_file.parent.mkdir(parents=True, exist_ok=True)
            with exclude_file.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(_LOCAL_EXCLUDES) + "\n")

    return "initialized"


def _untracked_files_report(repository_path: Path) -> str:
    """Show new files, which plain `git diff` silently omits."""

    completed = _git(
        repository_path, ["ls-files", "--others", "--exclude-standard"]
    )
    if completed.returncode != 0:
        return ""

    sections = []
    for relative in completed.stdout.splitlines()[:50]:
        path = (repository_path / relative).resolve()
        if path.is_symlink() or not path.is_relative_to(repository_path):
            continue
        try:
            content = path.read_text(encoding="utf-8")[:4000]
        except (UnicodeDecodeError, OSError):
            content = "(binary or unreadable file)"
        sections.append(f"+++ NEW FILE: {relative}\n{content}")

    return "\n\n".join(sections)


class GitStatusTool(BaseTool):
    name: str = "Repository Git Status"
    description: str = (
        "Read-only Git status inspection. Shows branch and changed files "
        "for a repository inside the workspace."
    )
    args_schema: type[BaseModel] = GitRepositoryInput

    def _run(self, repository_name: str) -> str:
        try:
            return _run_git(_repository_path(repository_name), ["status", "--short", "--branch"])
        except Exception as error:
            return f"GIT STATUS ERROR: {error}"


class GitDiffTool(BaseTool):
    name: str = "Repository Git Diff"
    description: str = (
        "Read-only Git diff inspection. Returns unstaged, staged, and new "
        "untracked file changes. "
        "Does not commit, push, reset, or modify the repository."
    )
    args_schema: type[BaseModel] = GitRepositoryInput

    def _run(self, repository_name: str) -> str:
        try:
            repository_path = _repository_path(repository_name)
            unstaged = _run_git(
                repository_path,
                ["diff", "--no-ext-diff", "--unified=3"],
            )
            staged = _run_git(
                repository_path,
                ["diff", "--cached", "--no-ext-diff", "--unified=3"],
            )
            output = (
                "UNSTAGED CHANGES:\n"
                + unstaged
                + "\n\nSTAGED CHANGES:\n"
                + staged
            )
            untracked = _untracked_files_report(repository_path)
            if untracked:
                output += "\n\nUNTRACKED (NEW) FILES:\n" + untracked
            if len(output) > 16000:
                output = output[:16000] + "\n... diff truncated ..."
            return output
        except Exception as error:
            return f"GIT DIFF ERROR: {error}"
