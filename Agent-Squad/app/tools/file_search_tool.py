import os
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


# INPUT SCHEMA

class FileSearchInput(BaseModel):

    repository_name: str = Field(
        ...,
        description="Name of the repository inside the workspace."
    )

    search_query: str = Field(
        ...,
        description="Filename or partial filename to search for."
    )

    extension: str = Field(
        default="",
        description="Optional file extension filter, such as .py or .json."
    )

    max_results: int = Field(
        default=100,
        ge=1,
        le=200,
        description="Maximum number of search results."
    )


# FILE SEARCH TOOL

class FileSearchTool(BaseTool):

    name: str = "Repository File Search"

    description: str = (
        "Search for files inside a repository using filename or extension. "
        "Supports recursive directory searching."
    )

    args_schema: type[BaseModel] = FileSearchInput

    def _run(
        self,
        repository_name: str,
        search_query: str,
        extension: str = "",
        max_results: int = 100
    ) -> str:

        try:

            # VALIDATE REPOSITORY

            repository_path = (
                WORKSPACE_ROOT / repository_name
            ).resolve()

            if not repository_path.is_relative_to(WORKSPACE_ROOT):
                return "Error: Invalid repository path."

            if not repository_path.is_dir():
                return "Error: Repository does not exist."

            if not search_query.strip():
                return "Error: Search query cannot be empty."

            # IGNORED DIRECTORIES

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

            results = []

            # RECURSIVE SEARCH

            for root, directories, files in os.walk(
                repository_path,
                followlinks=False
            ):

                directories[:] = [
                    directory
                    for directory in directories
                    if directory not in ignored
                    and not (Path(root) / directory).is_symlink()
                ]

                for filename in sorted(files):

                    if filename not in filename_match(filename, search_query):
                        continue

                    if extension:
                        normalized_extension = (
                            extension if extension.startswith(".")
                            else f".{extension}"
                        )

                        if Path(filename).suffix.lower() != normalized_extension.lower():
                            continue

                    file_path = Path(root) / filename

                    if file_path.is_symlink():
                        continue

                    relative_path = file_path.relative_to(
                        repository_path
                    )

                    results.append(str(relative_path))

                    if len(results) >= max_results:
                        break

                if len(results) >= max_results:
                    break

            if not results:
                return "No matching files found."

            return (
                f"Files found: {len(results)}\n\n"
                + "\n".join(f"[FILE] {path}" for path in results)
            )

        except Exception as error:

            return f"File search failed: {error}"


def filename_match(filename: str, query: str) -> list:
    """Return a match when the query appears in the filename."""

    return (
        [filename]
        if query.casefold() in filename.casefold()
        else []
    )