import subprocess

from app.tools.git_tools import GitDiffTool, GitStatusTool, ensure_git_baseline


def git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True
    ).stdout


def test_baseline_initializes_plain_folder(temp_repo):
    name, path = temp_repo
    (path / "main.py").write_text("print('hi')\n")

    assert ensure_git_baseline(name) == "initialized"

    assert (path / ".git").is_dir()
    assert "Agent Squad baseline" in git(path, "log", "--oneline")
    # Nothing is added to the user's working tree (no .gitignore etc.).
    assert sorted(p.name for p in path.iterdir()) == [".git", "main.py"]


def test_existing_repository_is_left_alone(temp_repo):
    name, path = temp_repo
    subprocess.run(["git", "init"], cwd=path, capture_output=True)

    assert ensure_git_baseline(name) == "existing"
    assert git(path, "log", "--oneline") == ""  # no commit was made for them


def test_baseline_rejects_paths_outside_workspace():
    try:
        ensure_git_baseline("..")
    except ValueError:
        return

    raise AssertionError("expected ValueError for a path outside the workspace")


def test_diff_tool_shows_modified_and_new_files(temp_repo):
    name, path = temp_repo
    (path / "main.py").write_text("VALUE = 1\n")
    ensure_git_baseline(name)

    (path / "main.py").write_text("VALUE = 2\n")
    (path / "health.py").write_text("def health():\n    return 'ok'\n")

    diff = GitDiffTool()._run(name)

    assert "-VALUE = 1" in diff and "+VALUE = 2" in diff
    # Plain `git diff` would silently omit this brand-new file.
    assert "NEW FILE: health.py" in diff
    assert "def health()" in diff

    status = GitStatusTool()._run(name)
    assert "main.py" in status and "health.py" in status


def test_caches_do_not_pollute_the_diff(temp_repo):
    name, path = temp_repo
    (path / "main.py").write_text("x = 1\n")
    ensure_git_baseline(name)

    (path / "__pycache__").mkdir()
    (path / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00\x01")
    (path / ".pytest_cache").mkdir()
    (path / ".pytest_cache" / "x").write_text("cache")

    assert "pycache" not in GitDiffTool()._run(name)
    assert ".pytest_cache" not in GitStatusTool()._run(name)
