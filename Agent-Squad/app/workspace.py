from app.tools.repository_tools import WORKSPACE_ROOT


def repository_exists(repository_name: str) -> bool:
    """True when the name is a real directory inside workspace/repositories."""

    if not repository_name or not repository_name.strip():
        return False

    path = (WORKSPACE_ROOT / repository_name).resolve()

    return (
        path != WORKSPACE_ROOT
        and path.is_relative_to(WORKSPACE_ROOT)
        and path.is_dir()
    )
