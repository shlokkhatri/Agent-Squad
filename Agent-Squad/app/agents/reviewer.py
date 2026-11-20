from crewai import Agent

from app.llm_config import llm
from app.tools.file_tools import FileReadTool
from app.tools.code_search_tool import CodeSearchTool
from app.tools.git_tools import GitStatusTool, GitDiffTool


def reviewer_agent() -> Agent:
    return Agent(
        role="Senior Code Reviewer",
        goal=(
            "Review implementation against the original request and "
            "implementation plan; identify correctness, security, "
            "maintainability, and regression risks."
        ),
        backstory=(
            "You are a senior production code reviewer. You inspect actual "
            "changed files and repository diffs, provide actionable findings "
            "with file paths and line references where possible, and never "
            "approve code without evidence. Separate blockers from suggestions."
        ),
        tools=[
            FileReadTool(),
            CodeSearchTool(),
            GitStatusTool(),
            GitDiffTool(),
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=7,
    )
