import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

from pathlib import Path
from urllib.parse import urlparse, urlencode

from dotenv import load_dotenv

from app.tools.repository_tools import WORKSPACE_ROOT


load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_API_URL = "https://api.github.com"


class GithubIntegrationError(Exception):
    """Raised when a GitHub operation fails."""



def validate_github_url(repository_url: str):
    """Validate and extract owner/repository from a GitHub URL."""

    if not isinstance(repository_url, str):
        raise GithubIntegrationError("Repository URL must be a string.")

    parsed = urlparse(repository_url.strip())

    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        raise GithubIntegrationError(
            "Only valid HTTPS GitHub repository URLs are supported."
        )

    parts = [
        part
        for part in parsed.path.strip("/").split("/")
        if part
    ]

    if len(parts) != 2:
        raise GithubIntegrationError(
            "Expected URL format: "
            "https://github.com/owner/repository"
        )

    owner, repository = parts
    repository = repository.removesuffix(".git")

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner):
        raise GithubIntegrationError("Invalid GitHub owner name.")

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise GithubIntegrationError("Invalid repository name.")

    if owner in {".", ".."} or repository in {".", ".."}:
        raise GithubIntegrationError("Invalid GitHub repository URL.")

    return owner, repository


def repository_directory_name(owner: str, repository: str) -> str:
    """Generate a deterministic repository directory name."""

    identity = f"{owner.lower()}/{repository.lower()}"

    suffix = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:8]

    return f"{owner}_{repository}_{suffix}"



def _require_token():
    if not GITHUB_TOKEN:
        raise GithubIntegrationError(
            "GITHUB_TOKEN is missing from the project .env file."
        )


def _create_git_environment():
    """Provide GitHub credentials through GIT_ASKPASS."""

    _require_token()

    temporary_directory = tempfile.TemporaryDirectory()

    askpass_path = (
        Path(temporary_directory.name) / "git-askpass.cmd"
    )

    askpass_path.write_text(
        "@echo off\r\n"
        "echo %~1 | findstr /I \"username\" >nul\r\n"
        "if not errorlevel 1 (\r\n"
        "    echo x-access-token\r\n"
        "    exit /b 0\r\n"
        ")\r\n"
        "echo %GITHUB_TOKEN%\r\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()

    environment["GIT_ASKPASS"] = str(askpass_path)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GITHUB_TOKEN"] = GITHUB_TOKEN

    return temporary_directory, environment



def _run_git(
    arguments,
    cwd=None,
    environment=None,
    timeout=120,
):
    """Execute a Git command safely."""

    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=environment or os.environ.copy(),
        )

    except subprocess.TimeoutExpired as exc:
        raise GithubIntegrationError(
            "Git operation timed out."
        ) from exc

    if result.returncode != 0:
        error_message = (
            result.stderr
            or result.stdout
            or "Git operation failed."
        ).strip()

        raise GithubIntegrationError(error_message)

    return result.stdout.strip()



def _github_api_request(
    method: str,
    endpoint: str,
    payload=None,
):
    """Send an authenticated GitHub REST API request."""

    _require_token()

    url = f"{GITHUB_API_URL}{endpoint}"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Agent-Squad",
    }

    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            response_data = response.read()

            if not response_data:
                return {}

            return json.loads(response_data.decode("utf-8"))

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            error_data = json.loads(error_body)
            message = error_data.get("message", error_body)
        except json.JSONDecodeError:
            message = error_body

        raise GithubIntegrationError(
            f"GitHub API error ({exc.code}): {message}"
        ) from exc

    except urllib.error.URLError as exc:
        raise GithubIntegrationError(
            f"Unable to connect to GitHub: {exc.reason}"
        ) from exc


def detect_default_branch(repository_url: str) -> str:
    """Detect the repository's actual default branch."""

    owner, repository = validate_github_url(repository_url)

    result = _github_api_request(
        "GET",
        f"/repos/{owner}/{repository}",
    )

    default_branch = result.get("default_branch")

    if not default_branch:
        raise GithubIntegrationError(
            "Unable to detect the repository's default branch."
        )

    return default_branch


def clone_repository(
    repository_url,
    base_branch,
):
    """Clone a GitHub repository into the Agent Squad workspace."""

    owner, repository = validate_github_url(repository_url)

    if not base_branch:
        base_branch = detect_default_branch(repository_url)

    if not base_branch.strip():
        raise GithubIntegrationError(
            "Base branch can not be empty."
        )

    directory_name = repository_directory_name(
        owner,
        repository
    )

    workspace_root = WORKSPACE_ROOT.resolve()

    workspace_root.mkdir(
        parents=True,
        exist_ok=True
    )

    repository_path = (
        workspace_root / directory_name
    ).resolve()

    if not repository_path.is_relative_to(workspace_root):

        raise GithubIntegrationError(
            "Repository destination is outside the workspace"
        )

    if repository_path.exists():
        raise GithubIntegrationError(
            f"Repository already exists locally: {directory_name}"
        )

    temporary_directory = None

    try :
        temporary_directory, environment = (
            _create_git_environment()
        )

        _run_git(
            [
                "clone",
                "--branch",
                base_branch,
                "--single-branch",
                "--",
                f"https://github.com/{owner}/{repository}.git",
                str(repository_path),
            ],
            cwd=workspace_root,
            environment= environment,
            timeout=600
        )

        return {
            "repository_name" : directory_name,
            "repository_url" : (
                f"https://github.com/{owner}/{repository}"
            ),
            "owner" : owner,
            "name" : repository,
            "base_branch" : base_branch,
            "local_path" : str(repository_path),
            "status" : "cloned",
        }        


    except Exception:
        if repository_path.exists():
            shutil.rmtree(
                repository_path,
                ignore_errors=True
            )
        raise

    finally:
        if temporary_directory:
            temporary_directory.cleanup()

# Development branch

def create_development_branch(
    repository_name,
    branch_name,
):

    """Create and checkout a new development branch."""
    
    workspace_root = WORKSPACE_ROOT.resolve()

    repository_path = (
        workspace_root / repository_name
    ).resolve()

    if (
        repository_path == workspace_root
        or not repository_path.is_relative_to(workspace_root)
        or not repository_path.is_dir()
    ):
        raise GithubIntegrationError(
            "Repository does not exists inside the workspace."
        )

    if (
        not branch_name
        or not re.fullmatch(
            r"[A-Za-z0-9._/-]+",
            branch_name,
        )
        or branch_name.startswith("-")
    ):
        raise GithubIntegrationError(
            "Invalid Git branch name. "
        )

    if not branch_name.startswith("agent_squad/"):
        raise GithubIntegrationError(
            "Only Agent Squad development branches are allowed."
        )

    _run_git(
        [
            "check-ref-format",
            "--branch",
            branch_name,
        ],
        cwd = repository_path,
    )

    _run_git(
        [
            "switch",
            "-c",
            branch_name
        ],
        cwd = repository_path
    )

    return branch_name



def commit_changes(
    repository_name,
    commit_message,
):
    """Safely commit changes from an Agent Squad development branch."""

    repository_path = (
        WORKSPACE_ROOT / repository_name
    ).resolve()

    workspace_root = WORKSPACE_ROOT.resolve()

    if (
        not repository_path.is_relative_to(workspace_root)
        or repository_path == workspace_root
        or not (repository_path / ".git").exists()
    ):
        raise GithubIntegrationError(
            "Invalid Git repository."
        )

    if not commit_message or not commit_message.strip():
        raise GithubIntegrationError(
            "Commit message cannot be empty."
        )

    # Ensure commits are made only on Agent Squad branches.
    current_branch = _run_git(
        ["branch", "--show-current"],
        cwd=repository_path,
    )

    if not current_branch.startswith("agent_squad/"):
        raise GithubIntegrationError(
            "Commits are allowed only on Agent Squad development branches."
        )

    status = _run_git(
        ["status", "--porcelain"],
        cwd=repository_path,
    )

    if not status:
        return {
            "status": "no_changes",
            "commit": None,
        }

    # Stage repository changes.
    _run_git(
        ["add", "-A"],
        cwd=repository_path,
    )

    # Inspect staged files before committing.
    staged_files = _run_git(
        ["diff", "--cached", "--name-only"],
        cwd=repository_path,
    )

    sensitive_patterns = (
        ".env",
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    )

    sensitive_files = []

    for file_path in staged_files.splitlines():
        normalized_path = file_path.strip().replace("\\", "/")
        filename = normalized_path.split("/")[-1].lower()

        if (
            filename in sensitive_patterns
            or filename.startswith(".env.")
            or filename.endswith(".pem")
            or filename.endswith(".key")
            or filename.endswith(".p12")
            or filename.endswith(".pfx")
        ):
            sensitive_files.append(file_path)

    if sensitive_files:
        # Remove staged changes without deleting working files.
        _run_git(
            ["reset"],
            cwd=repository_path,
        )

        raise GithubIntegrationError(
            "Commit blocked because sensitive files were detected: "
            + ", ".join(sensitive_files)
        )

    _run_git(
        [
            "-c",
            "user.name=Agent Squad",
            "-c",
            "user.email=agent-squad@users.noreply.github.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            commit_message.strip(),
        ],
        cwd=repository_path,
    )

    commit_hash = _run_git(
        ["rev-parse", "HEAD"],
        cwd=repository_path,
    )

    return {
        "status": "committed",
        "commit": commit_hash,
    }


def push_development_branch(
    repository_name,
    branch_name,
):

    """Push the development branch to github."""

    repository_path = (
        WORKSPACE_ROOT / repository_name
    ).resolve()

    if (
        not repository_path.is_relative_to(WORKSPACE_ROOT.resolve())
        or repository_path == WORKSPACE_ROOT.resolve()
        or not (repository_path / ".git").exists()
    ):
        raise GithubIntegrationError(
            "Invalid Git repository."
        )

    current_branch = _run_git(
        ["branch","--show-current"],
        cwd = repository_path,
    )

    if current_branch != branch_name:
        raise GithubIntegrationError(
            "Refusing to push: current branch does not match"
            "the requested development branch."
        )

    if not branch_name.startswith("agent_squad/"):
        raise GithubIntegrationError(
            "Only Agent Squad development branches can be pushed."
        )

    temporary_directory = None

    try :

        temporary_directory, environment = (
            _create_git_environment()
        )

        _run_git(
            [
                "push",
                "--set-upstream",
                "origin",
                branch_name
            ],
            cwd = repository_path,
            environment=environment,
            timeout=600,
        )

    finally:

        if temporary_directory:
            temporary_directory.cleanup()

    return{
        "status" : "pushed",
        "branch" : branch_name
    }


# Create pull request

def create_pull_request(
    repository_url,
    base_branch,
    development_branch,
    title,
    body,
):
    """Create a GitHub PR or return an existing open PR."""

    owner, repository = validate_github_url(repository_url)

    if not base_branch or not development_branch:
        raise GithubIntegrationError(
            "Base branch and development branch are required."
        )

    if base_branch == development_branch:
        raise GithubIntegrationError(
            "Base and development branches cannot be identical."
        )

    if not development_branch.startswith("agent_squad/"):
        raise GithubIntegrationError(
            "Invalid Agent Squad development branch."
        )

    if not title or not title.strip():
        raise GithubIntegrationError(
            "Pull Request title cannot be empty."
        )

    # Check whether an open PR already exists.
    query = urlencode({
        "state": "open",
        "head": f"{owner}:{development_branch}",
        "base": base_branch,
    })

    existing_prs = _github_api_request(
        "GET",
        f"/repos/{owner}/{repository}/pulls?{query}",
    )

    if existing_prs:
        existing = existing_prs[0]

        return {
            "status": "already_exists",
            "pull_request_number": existing.get("number"),
            "pull_request_url": existing.get("html_url"),
            "title": existing.get("title"),
            "state": existing.get("state"),
        }

    # Create a new PR.
    result = _github_api_request(
        "POST",
        f"/repos/{owner}/{repository}/pulls",
        {
            "title": title.strip(),
            "head": development_branch,
            "base": base_branch,
            "body": body,
        },
    )

    return {
        "status": "created",
        "pull_request_number": result.get("number"),
        "pull_request_url": result.get("html_url"),
        "title": result.get("title"),
        "state": result.get("state"),
    }