from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


# INPUT SCHEMA

class FileWriteInput(BaseModel):

    repository_name: str = Field(
        ...,
        description="Name of the repository inside the workspace."
    )

    file_path: str = Field(
        ...,
        description="Relative path of the file to create or update."
    )

    content: str = Field(
        ...,
        description="Content to write into the file."
    )

    overwrite: bool = Field(
        default=False,
        description="Allow overwriting an existing file."
    )


# FILE WRITER TOOL

class FileWriteTool(BaseTool):

    name: str = "Repository File Writer"

    description: str = (
        "Create or update a text file inside a controlled repository. "
        "Can create missing directories and prevents accidental overwrites."
    )

    args_schema: type[BaseModel] = FileWriteInput

    def _run(
        self,
        repository_name: str,
        file_path: str,
        content: str,
        overwrite: bool = False
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

            # VALIDATE TARGET FILE

            target_file = (
                repository_path / file_path
            ).resolve()

            if not target_file.is_relative_to(repository_path):
                return "Error: Access outside repository is prohibited."

            if target_file.exists() and target_file.is_dir():
                return "Error: Target path is a directory."

            # PREVENT ACCIDENTAL OVERWRITING

            if target_file.exists() and not overwrite:
                return (
                    f"Error: File already exists: {file_path}. "
                    "Set overwrite=True to replace it."
                )

            # CREATE PARENT DIRECTORIES

            target_file.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            # WRITE CONTENT

            target_file.write_text(
                content,
                encoding="utf-8"
            )

            return (
                f"File written successfully!\n"
                f"Repository: {repository_name}\n"
                f"File: {file_path}\n"
                f"Size: {target_file.stat().st_size} bytes"
            )

        except Exception as error:

            return f"File writing failed: {error}"