from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


# INPUT SCHEMA

class FileDeleteInput(BaseModel):

    repository_name: str = Field(
        ...,
        description="Name of the repository inside the workspace."
    )

    file_path: str = Field(
        ...,
        description="Relative path of the file to delete."
    )

    confirm: bool = Field(
        default=False,
        description="Explicitly confirm file deletion."
    )


# FILE DELETE TOOL

class FileDeleteTool(BaseTool):

    name: str = "Repository File Deleter"

    description: str = (
        "Delete a specific file inside a controlled repository. "
        "Requires explicit confirmation and prevents directory deletion."
    )

    args_schema: type[BaseModel] = FileDeleteInput

    def _run(
        self,
        repository_name: str,
        file_path: str,
        confirm: bool = False
    ) -> str:

        try:

            if not confirm:
                return "Error: File deletion requires confirmation."

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

            if not target_file.exists():
                return f"Error: File not found: {file_path}"

            if not target_file.is_file():
                return "Error: Directory deletion is not permitted."

            # DELETE FILE

            target_file.unlink()

            return (
                f"File deleted successfully!\n"
                f"Repository: {repository_name}\n"
                f"File: {file_path}"
            )

        except Exception as error:

            return f"File deletion failed: {error}"