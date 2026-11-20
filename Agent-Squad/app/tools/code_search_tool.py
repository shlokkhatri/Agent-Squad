import os
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


# INPUT SCHEMA

class CodeSearchInput(BaseModel):

    repository_name: str = Field(
        ...,
        description="Name of the repository inside the workspace."
    )

    search_query: str = Field(
        ...,
        description="Text, function name, class name, or variable to search."
    )

    file_extensions: str = Field(
        default=".py,.js,.ts,.jsx,.tsx,.java,.cpp,.c,.html,.css",
        description="Comma-separated source file extensions."
    )

    max_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of matching lines."
    )


# CODE SEARCH TOOL

class CodeSearchTool(BaseTool):

    name: str = "Repository Code Search"

    description: str = (
        "Search for specific text inside source code files. "
        "Returns matching filenames, line numbers, and code snippets."
    )

    args_schema: type[BaseModel] = CodeSearchInput

    def _run(
        self,
        repository_name: str,
        search_query: str,
        file_extensions: str = ".py,.js,.ts,.jsx,.tsx,.java,.cpp,.c,.html,.css",
        max_results: int = 50
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

            # CONFIGURATION

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

            allowed_extensions = {
                item.strip().lower()
                for item in file_extensions.split(",")
                if item.strip()
            }

            results = []

            # SEARCH SOURCE CODE

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

                    file_path = Path(root) / filename

                    if file_path.is_symlink():
                        continue

                    if file_path.suffix.lower() not in allowed_extensions:
                        continue

                    try:

                        if file_path.stat().st_size > 1_000_000:
                            continue

                        content = file_path.read_text(
                            encoding="utf-8"
                        )

                    except (UnicodeDecodeError, OSError):
                        continue

                    for line_number, line in enumerate(
                        content.splitlines(),
                        start=1
                    ):

                        if search_query.casefold() in line.casefold():

                            relative_path = file_path.relative_to(
                                repository_path
                            )

                            results.append(
                                f"[MATCH] {relative_path}:{line_number}\n"
                                f"         {line.strip()}"
                            )

                            if len(results) >= max_results:
                                break

                    if len(results) >= max_results:
                        break

                if len(results) >= max_results:
                    break

            if not results:
                return "No matching code found."

            return (
                f"Code matches found: {len(results)}\n\n"
                + "\n\n".join(results)
            )

        except Exception as error:

            return f"Code search failed: {error}"