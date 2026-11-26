from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


WORKSPACE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "workspace"
    / "repositories"
).resolve()


# INPUT SCHEMA

class RepositoryInput(BaseModel):

    repository_name: str = Field(
        ...,
        description="Name of the repository inside workspace/repositories."
    )


# REPOSITORY STRUCTURE TOOL

class RepositoryStructureTool(BaseTool):

    name: str = "Repository Structure Inspector"

    description: str = (
        "Inspect the directory structure of a repository. "
        "Return folders and files while excluding virtual environments, "
        "Git metadata, caches, and dependency directories."
    )

    args_schema: type[BaseModel] = RepositoryInput

    def _run(self, repository_name: str) -> str:

        try:

            repository_path = (
                WORKSPACE_ROOT / repository_name
            ).resolve()

            # SECURITY VALIDATION

            if(
                repository_path == WORKSPACE_ROOT
                or not repository_path.is_relative_to(WORKSPACE_ROOT)
            ):
                return "Error: Access outside WORKSPACE is prohibited."

            if not repository_path.is_dir():
                return f"Repository '{repository_name}' not found."

            # DIRECTORIES TO IGNORE

            ignored = {
                ".git",
                ".venv",
                "venv",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
                ".idea",
                ".vscode",
                "dist",
                "build"
            }

            output = []

            for current_path in sorted(repository_path.rglob("*")):

                relative_path = current_path.relative_to(repository_path)

                # Skip ignored directories and their contents.

                if any(part in ignored for part in relative_path.parts):
                    continue

                if len(output) >= 200:
                    output.append("... File listing truncated.")
                    break

                if current_path.is_dir():
                    output.append(f"[DIR] {relative_path}")

                else:
                    output.append(f"[FILE] {relative_path}")

            if not output:
                return "Repository is empty."

            return "\n".join(output)

        except Exception as error:

            return f"Repository inspection failed: {error}"