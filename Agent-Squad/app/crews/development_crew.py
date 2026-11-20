from crewai import Crew, Process, Task

from app.agents.orchestrator import orchestrator_agent
from app.agents.planner import planner_agent
from app.agents.coder import coder_agent
from app.agents.reviewer import reviewer_agent
from app.agents.tester import tester_agent


class DevelopmentCrew:
    """Builds the initial and corrective development crews."""

    def initial_crew(self) -> Crew:
        orchestrator = orchestrator_agent()
        planner = planner_agent()
        coder = coder_agent()
        reviewer = reviewer_agent()
        tester = tester_agent()

        intake_task = Task(
            description=(
                "Analyze the incoming development request.\n\n"
                "Repository: {repository_name}\n"
                "User request: {user_request}\n\n"
                "Establish acceptance criteria, constraints, and "
                "verification requirements."
            ),
            expected_output="A concise execution brief.",
            agent=orchestrator,
        )

        planning_task = Task(
            description=(
                "Inspect repository '{repository_name}' using your tools.\n\n"
                "User request: {user_request}\n\n"
                "Use the execution brief as context. Identify relevant files, "
                "required changes, risks, and validation steps. "
                "Do not modify files."
            ),
            expected_output="A repository-backed implementation plan.",
            agent=planner,
            context=[intake_task],
        )

        implementation_task = Task(
            description=(
                "Implement the request in repository '{repository_name}'.\n\n"
                "User request: {user_request}\n\n"
                "Follow the plan. Read files before editing. Use repository "
                "tools, preserve unrelated code, and avoid deleting files. "
                "Report the actual files changed."
            ),
            expected_output="Implementation summary and changed file paths.",
            agent=coder,
            context=[intake_task, planning_task],
        )

        review_task = Task(
            description=(
                "Review the actual implementation in '{repository_name}'. "
                "Inspect source files and Git diff. Identify correctness, "
                "security, and regression issues. Classify findings as "
                "BLOCKER, MAJOR, MINOR, or SUGGESTION. Do not modify files."
            ),
            expected_output=(
                "Review findings with severity, evidence, and required fixes."
            ),
            agent=reviewer,
            context=[intake_task, planning_task, implementation_task],
        )

        revision_task = Task(
            description=(
                "Fix actionable BLOCKER and MAJOR findings from the review "
                "in repository '{repository_name}'. Fix MINOR findings when "
                "safe and within scope. Re-read files before editing. "
                "Do not claim changes you did not make."
            ),
            expected_output="Revision summary and unresolved findings.",
            agent=coder,
            context=[intake_task, planning_task, implementation_task, review_task],
        )

        final_review_task = Task(
            description=(
                "Inspect the current implementation and Git diff in "
                "'{repository_name}'. Verify whether earlier BLOCKER and "
                "MAJOR findings are resolved. Do not modify files. "
                "State APPROVED or CHANGES REQUIRED with evidence."
            ),
            expected_output="Final review outcome and remaining findings.",
            agent=reviewer,
            context=[
                intake_task,
                planning_task,
                implementation_task,
                review_task,
                revision_task,
            ],
        )

        testing_task = Task(
            description=(
                "Execute the repository tests using the Repository Pytest "
                "Runner tool for '{repository_name}'.\n\n"
                "Inspect the repository test layout first. If a tests "
                "directory exists, run it. Otherwise select the relevant "
                "existing test file, such as test_main.py. Do not invent "
                "test results.\n\n"
                "Include the exact tool output, especially the line "
                "'TEST STATUS: PASSED' or 'TEST STATUS: FAILED'. "
                "If execution is impossible, report NOT RUN."
            ),
            expected_output=(
                "Actual pytest tool output, test status, and exit code."
            ),
            agent=tester,
            context=[
                intake_task,
                planning_task,
                implementation_task,
                revision_task,
                final_review_task,
            ],
        )

        return Crew(
            agents=[orchestrator, planner, coder, reviewer, tester],
            tasks=[
                intake_task,
                planning_task,
                implementation_task,
                review_task,
                revision_task,
                final_review_task,
                testing_task,
            ],
            process=Process.sequential,
            verbose=False,
        )

    def correction_crew(self) -> Crew:
        """Creates one bounded correction-and-review cycle.

        Tests are re-run by the flow itself after this crew finishes, so the
        result is real pytest output rather than an LLM's report of it.
        """

        coder = coder_agent()
        reviewer = reviewer_agent()

        correction_task = Task(
            description=(
                "The previous test execution failed in repository "
                "'{repository_name}'.\n\n"
                "Original request: {user_request}\n\n"
                "Previous test output:\n"
                "{test_feedback}\n\n"
                "Inspect the failing tests and relevant source files. "
                "Identify the root cause and make the smallest necessary "
                "correction using your repository tools. Preserve unrelated "
                "code. Do not modify tests merely to hide a real defect. "
                "Report exactly what you changed."
            ),
            expected_output=(
                "Root cause, correction details, and files changed."
            ),
            agent=coder,
        )

        review_task = Task(
            description=(
                "Review the latest correction in repository "
                "'{repository_name}'. Inspect the changed source and Git diff. "
                "Check whether the correction addresses the reported test "
                "failure without introducing obvious regressions. "
                "Do not modify files."
            ),
            expected_output="Correction review with findings.",
            agent=reviewer,
            context=[correction_task],
        )

        return Crew(
            agents=[coder, reviewer],
            tasks=[
                correction_task,
                review_task,
            ],
            process=Process.sequential,
            verbose=False,
        )   