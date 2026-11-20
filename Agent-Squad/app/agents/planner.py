from crewai import Agent

from app.llm_config import llm
from app.tools.repository_tools import RepositoryStructureTool
from app.tools.file_tools import FileReadTool
from app.tools.file_search_tool import FileSearchTool
from app.tools.code_search_tool import CodeSearchTool


def planner_agent() -> Agent:
    return Agent(
        role="Senior Software Architect",
        goal=(
            "Inspect the target repository and produce a precise, "
            "minimal implementation plan grounded in the actual codebase."
        ),
        backstory=(
            "You are an experienced software architect specializing in "
            "Python, FastAPI, databases, and maintainable software design. "
            "You inspect the repository before planning, identify relevant "
            "files and dependencies, and never invent files or APIs."
        ),
        tools=[
            RepositoryStructureTool(),
            FileReadTool(),
            FileSearchTool(),
            CodeSearchTool(),
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=8,
    )
