from app.agents.planner import planner_agent
from app.agents.coder import coder_agent
from app.agents.reviewer import reviewer_agent
from app.agents import tester as tester_module
from app.agents.orchestrator import orchestrator_agent


def test_agent_creation():

    print("\n========== AGENT SQUAD ==========\n")

    agents = {

        "Orchestrator": orchestrator_agent(),

        "Planner": planner_agent(),

        "Coder": coder_agent(),

        "Reviewer": reviewer_agent(),

        "Tester": tester_module.tester_agent()

    }

    for name, agent in agents.items():

        print(f"\n{name} Agent: CREATED")

        print(f"Role: {agent.role}")

    print("\nAll five agents initialized successfully!☻")


if __name__ == "__main__":

    test_agent_creation()