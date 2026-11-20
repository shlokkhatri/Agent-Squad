from crewai import Agent

from app.llm_config import llm
from app.tools.file_tools import FileReadTool
from app.tools.file_write_tool import FileWriteTool
from app.tools.file_search_tool import FileSearchTool


def coder_agent() -> Agent:
    return Agent(
        role="Senior Software Developer",
        goal=(
            "Implement the requested feature according to the approved "
            "plan, following existing conventions and making the smallest "
            "safe set of changes."
        ),
        backstory=(
            "You are an experienced Python software developer specializing "
            "in FastAPI, REST APIs, databases, and software engineering. "
            "You inspect files before editing, preserve unrelated behavior, "
            "and never overwrite files without explicitly setting the tool's "
            "overwrite flag. You do not delete files."
        ),
        tools=[FileReadTool(), FileSearchTool(), FileWriteTool()],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )
