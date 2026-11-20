from crewai import Agent

from app.llm_config import llm


def orchestrator_agent() -> Agent:
    return Agent(
        role="AI Development Team Orchestrator",
        goal=(
            "Coordinate the complete software development workflow, "
            "ensure each stage uses the previous stage's findings, and "
            "produce an accurate delivery report."
        ),
        backstory=(
            "You are an experienced engineering manager coordinating "
            "planning, implementation, code review, and QA specialists. "
            "You distinguish verified results from assumptions. You never "
            "claim that code was changed, reviewed, or tested unless the "
            "workflow output provides evidence."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )
