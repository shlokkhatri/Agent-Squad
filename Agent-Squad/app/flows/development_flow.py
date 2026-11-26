import re

from pydantic import BaseModel, Field
from crewai.flow import Flow, start

from app.crews.development_crew import DevelopmentCrew
from app.tools.git_tools import ensure_git_baseline
from app.tools.testing_tools import run_pytest
from app.workspace import repository_exists


MAX_CORRECTION_RETRIES = 2

# Index of the final-review task inside the initial crew's task list.
FINAL_REVIEW_TASK_INDEX = 5


class DevelopmentState(BaseModel):
    user_request: str = ""
    repository_name: str = ""
    status: str = "pending"
    stage: str = "pending"
    final_report: str = ""
    error: str = ""
    error_code: str = ""

    test_status: str = "NOT RUN"
    correction_attempts: int = 0
    test_history: list[str] = Field(default_factory=list)

    review_verdict: str = "UNKNOWN"
    warnings: list[str] = Field(default_factory=list)

    @property
    def can_publish(self):
        return(
            self.test_status == "PASSED"
            and self.review_verdict == "APPROVED"
            and self.status == "completed"
        )


class DevelopmentFlow(Flow[DevelopmentState]):
    """Runs development, verified testing, and bounded automatic corrections.

    Test status is NOT taken from what an LLM says the tests did. After each
    crew run the flow executes pytest itself and uses that real result.
    """

    @staticmethod
    def extract_test_status(output: str) -> str:
        """Return the LAST explicit TEST STATUS marker in the text.

        The last one matters: later text may quote an earlier failure
        ("previous run: TEST STATUS: FAILED") before reporting a new result.
        """

        matches = re.findall(
            r"TEST STATUS:\s*(PASSED|FAILED|TIMEOUT|NOT RUN)",
            output,
            re.IGNORECASE,
        )

        if matches:
            return matches[-1].upper()

        return "UNKNOWN"

    @staticmethod
    def extract_review_verdict(
        result,
        task_index: int = FINAL_REVIEW_TASK_INDEX,
    ) -> str:
        """Extract the final review verdict from a specified task."""

        outputs = getattr(result, "tasks_output", None) or []

        if len(outputs) <= task_index:
            return "UNKNOWN"

        text = outputs[task_index].raw or ""

        if re.search(r"CHANGES\s+REQUIRED", text, re.IGNORECASE):
            return "CHANGES REQUIRED"

        if re.search(r"\bAPPROVED\b", text, re.IGNORECASE):
            return "APPROVED"

        return "UNKNOWN"

    @staticmethod
    def is_quota_error(error: Exception) -> bool:
        error_message = str(error).lower()

        if "ratelimit" in type(error).__name__.lower():
            return True

        quota_indicators = [
            "resource_exhausted",
            "quota exceeded",
            "requestsperday",
            "requestsperminute",
            "request_per_day",
            "request_per_minute",
            "requests_per_day",
            "rate_limit_exceeded",
            "rate limit",
        ]

        if any(indicator in error_message for indicator in quota_indicators):
            return True

        # A bare "429" would also match line numbers and ids, so require an
        # HTTP-looking context around it.
        return bool(
            re.search(r"(http|status|code|error)\D{0,12}429\b", error_message)
        )

    @staticmethod
    def extract_task_output(result) -> str:
        """Collect output from every completed task, in order."""

        # CrewAI's CrewOutput exposes `tasks_output` (plural).
        tasks_output = getattr(result, "tasks_output", None)

        if tasks_output:
            outputs = []

            for index, item in enumerate(tasks_output, start=1):
                outputs.append(
                    f"\n---------- Task {index} ----------\n"
                    f"{item.raw}"
                )

            return "\n".join(outputs)

        return getattr(result, "raw", None) or str(result)

    def verify_tests(self) -> str:
        """Run pytest directly and record the authoritative status."""

        self.state.stage = "verifying_tests"

        verification = run_pytest(self.state.repository_name)

        self.state.test_status = verification.status
        self.state.test_history.append(verification.status)

        return verification.format()

    def build_final_report(
        self,
        initial_output: str,
        correction_outputs: list[str],
        verified_output: str,
    ) -> str:
        """Build a delivery report without another LLM call."""

        lines = [
            "========== AGENT SQUAD FINAL REPORT ==========",
            "",
            f"Repository: {self.state.repository_name}",
            f"Request: {self.state.user_request}",
            "",
            "INITIAL DEVELOPMENT AND VALIDATION:",
            initial_output,
        ]

        if correction_outputs:
            lines.extend(["", "CORRECTION REPORTS:"])

            for index, output in enumerate(correction_outputs, start=1):
                lines.extend(["", f"Correction {index}:", output])

        lines.extend([
            "",
            f"FINAL REVIEW VERDICT: {self.state.review_verdict}",
            f"CORRECTION ATTEMPTS: {self.state.correction_attempts}",
            f"FINAL TEST STATUS (verified by direct pytest run): "
            f"{self.state.test_status}",
            "",
            "TEST EXECUTION HISTORY:",
        ])

        for index, status in enumerate(self.state.test_history, start=1):
            lines.append(f"Attempt {index}: {status}")

        lines.extend(["", "LAST VERIFIED TEST OUTPUT:", verified_output])

        if self.state.warnings:
            lines.extend(["", "WARNINGS:"])
            lines.extend(f"- {warning}" for warning in self.state.warnings)

        lines.extend(["", "========== END OF REPORT =========="])

        return "\n".join(lines)

    def fail(self, code: str, message: str) -> str:
        self.state.status = "failed"
        self.state.stage = "failed"
        self.state.error_code = code
        self.state.error = message
        self.state.final_report = (
            "Development workflow failed.\n"
            f"Reason: {message}"
        )
        return self.state.final_report

    @start()
    def execute_development(self) -> str:
        self.state.status = "running"
        self.state.stage = "preparing"

        if not repository_exists(self.state.repository_name):
            return self.fail(
                "REPOSITORY_NOT_FOUND",
                f"Repository '{self.state.repository_name}' was not found "
                "in workspace/repositories.",
            )

        try:
            # Reviewers rely on `git diff`; make sure there is a baseline.
            try:
                ensure_git_baseline(self.state.repository_name)
            except Exception as error:
                self.state.warnings.append(
                    "Git baseline could not be prepared; reviewers may not "
                    f"have diffs ({type(error).__name__}: {error})."
                )

            development_crew = DevelopmentCrew()

            print("\n========== INITIAL DEVELOPMENT ==========\n")
            self.state.stage = "initial_development"

            initial_result = development_crew.initial_crew().kickoff(
                inputs={
                    "repository_name": self.state.repository_name,
                    "user_request": self.state.user_request,
                }
            )

            initial_output = self.extract_task_output(initial_result)
            self.state.review_verdict = self.extract_review_verdict(
                initial_result
            )

            # What the Tester agent CLAIMED vs. what pytest actually does.
            claimed_status = self.extract_test_status(initial_output)
            verified_output = self.verify_tests()

            if (
                claimed_status != "UNKNOWN"
                and claimed_status != self.state.test_status
            ):
                self.state.warnings.append(
                    f"Tester agent reported {claimed_status} but the "
                    f"verified pytest run returned {self.state.test_status}. "
                    "The verified result is used."
                )

            correction_outputs = []

            while (
                self.state.test_status == "FAILED"
                and self.state.correction_attempts < MAX_CORRECTION_RETRIES
            ):
                self.state.correction_attempts += 1
                self.state.stage = (
                    f"correction_{self.state.correction_attempts}"
                )

                print(
                    f"\n========== CORRECTION "
                    f"{self.state.correction_attempts}/"
                    f"{MAX_CORRECTION_RETRIES} ==========\n"
                )

                correction_result = development_crew.correction_crew().kickoff(
                    inputs={
                        "repository_name": self.state.repository_name,
                        "user_request": self.state.user_request,
                        # Real pytest output, not an LLM's retelling of it.
                        "test_feedback": verified_output,
                    }
                )

                correction_outputs.append(
                    self.extract_task_output(correction_result)
                )

                # Update the final review verdict after the correction.
                self.state.review_verdict = self.extract_review_verdict(
                    correction_result,
                    task_index=1,
                )

                # Re-run actual pytest verification.
                verified_output = self.verify_tests()

            self.state.final_report = self.build_final_report(
                initial_output,
                correction_outputs,
                verified_output,
            )

            if self.state.test_status == "PASSED":
                if self.state.review_verdict == "CHANGES REQUIRED":
                    self.state.status = "completed_with_open_review_findings"
                else:
                    self.state.status = "completed"
            elif self.state.test_status == "FAILED":
                self.state.status = "completed_with_test_failures"
            else:
                self.state.status = "completed_with_unverified_tests"

            self.state.stage = "done"

            return self.state.final_report

        except Exception as error:
            if self.is_quota_error(error):
                return self.fail(
                    "QUOTA_EXCEEDED",
                    "GEMINI API quota exhausted. Wait for the quota reset "
                    "or use another available model.",
                )

            return self.fail(
                "UNEXPECTED_ERROR",
                f"{type(error).__name__} : {error}",
            )
