from pathlib import Path

from app.tools.repository_tools import WORKSPACE_ROOT

def repository_exists(repository_name):

    """Check whether a repository exists inside the workpalce."""

    if not repository_name or not repository_name.strip():
        return False

    workspace_root = WORKSPACE_ROOT.resolve()

    path = (workspace_root / repository_name).resolve()

    return(
        path != workspace_root
        and path.is_relative_to(workspace_root)
        and path.is_dir()
    )

def get_repository_path(repository_name):

    """Return a validate repository path."""

    if not repository_name or not repository_name.strip():
        raise ValueError(
            "Repository name can not be empty"
        )

    workspace_root = WORKSPACE_ROOT.resolve()

    path = (workspace_root / repository_name).resolve()

    if (
        path == workspace_root
        or not path.is_relative_to(workspace_root)
        or not path.is_dir()
    ):

        raise ValueError(
            f"Repository '{repository_name}' does not exist"
        )

    return path