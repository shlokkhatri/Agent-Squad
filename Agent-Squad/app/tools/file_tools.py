from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.repository_tools import WORKSPACE_ROOT


# INPUT SCHEMA

class FileReadInput(BaseModel):

    repository_name: str = Field(
        ...,
        description="Name of the repository inside the workspace."
    )

    file_path: str = Field(
        ...,
        description="Relative path of the file to read inside the repository."
    )


# FILE READER TOOL

class FileReadTool(BaseTool):

    name: str = "Repository File Reader"

    description: str = (
        "Read the content of a source file from a repository "
        "inside the controlled workspace. Only text files are supported."
    )

    args_schema: type[BaseModel] = FileReadInput

    def _run(
        self,
        repository_name: str,
        file_path: str
    ) -> str:

        try:

            # VALIDATE REPOSITORY PATH

            repository_path = (
                WORKSPACE_ROOT / repository_name
            ).resolve()

            if not repository_path.is_relative_to(WORKSPACE_ROOT):
                return "Error: Invalid repository path."

            if not repository_path.is_dir():
                return "Error: Repository does not exist."

            # VALIDATE FILE PATH

            target_file = (
                repository_path / file_path
            ).resolve()

            if not target_file.is_relative_to(repository_path):
                return "Error: Access outside repository is prohibited."

            if not target_file.is_file():
                return f"File not found: {file_path}"

            # FILE SIZE VALIDATION

            if target_file.stat().st_size > 50_000:
                return "Error: File exceeds the 50 KB reading limit."

            # READ FILE CONTENT

            content = target_file.read_text(
                encoding="utf-8"
            )

            return (
                f"FILE: {file_path}\n\n"
                f"CONTENT:\n{content}"
            )

        except UnicodeDecodeError:
            return "Error: File is not a supported UTF-8 text file."

        except Exception as error:
            return f"File reading failed: {error}"