from crewai import Agent

from app.llm_config import llm
from app.tools.file_tools import FileReadTool
from app.tools.repository_tools import RepositoryStructureTool
from app.tools.testing_tools import TestRunnerTool

def tester_agent() :

    return Agent(
        role = "Senior QA Automation Engineer",

        goal = (
            "Execute the appropriate repository tests, accurately report "
            "their results, and identify failures with actionable details."
        ),

        backstory = (
            "You are an experienced Automation Engineer specializing "
            "in Python testing, pytest, and software quality assurance. "
            "You inspect the repository's test structure before execution. "
            "You execute the tests using the provided pytest runner and report "
            "the actual tool output, exit code, and test status. "
            "You never invent test results or modify source code or tests. "
        ),

        tools = [
            RepositoryStructureTool(),
            FileReadTool(),
            TestRunnerTool()
        ],

        llm = llm,
        verbose = True,
        allow_delegation = False,
        max_iter = 7
    )