import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.classifier_agent.agent import root_agent as classifier_agent
from agents.duplicate_check_agent.agent import root_agent as duplicate_check_agent
from agents.drafting_agent.agent import root_agent as drafting_agent
from agents.verifier_agent.agent import root_agent as verifier_agent
from agents.escalation_agent.agent import root_agent as escalation_agent
from agents.coordinator_agent.agent import root_agent as coordinator_agent
from agents.vision_agent.agent import root_agent as vision_agent
from agents.translation_agent.agent import root_agent as translation_agent
from agents.awareness_agent.agent import root_agent as awareness_agent

def test_agents_initialization():
    # Verify Classifier Agent and Skill integration
    assert classifier_agent.name == "classifier_agent"
    assert classifier_agent.model == "gemini-3.1-flash-lite"
    assert classifier_agent.output_schema is not None
    assert len(classifier_agent.tools) > 0
    # Check that a SkillToolset tool is available
    assert any(tool.__class__.__name__ == "SkillToolset" for tool in classifier_agent.tools)
    
    # Verify Duplicate Check Agent
    assert duplicate_check_agent.name == "duplicate_check_agent"
    assert duplicate_check_agent.model == "gemini-3.1-flash-lite"
    assert duplicate_check_agent.output_schema is not None
    
    # Verify Drafting Agent and Skill integration
    assert drafting_agent.name == "drafting_agent"
    assert drafting_agent.model == "gemini-3.1-flash-lite"
    assert drafting_agent.output_schema is not None
    assert len(drafting_agent.tools) > 0
    assert any(tool.__class__.__name__ == "SkillToolset" for tool in drafting_agent.tools)
    
    # Verify Verifier Agent
    assert verifier_agent.name == "verifier_agent"
    assert verifier_agent.model == "gemini-3.1-flash-lite"
    assert verifier_agent.output_schema is not None
    
    # Verify Escalation Agent
    assert escalation_agent.name == "escalation_agent"
    assert escalation_agent.model == "gemini-3.1-flash-lite"
    assert escalation_agent.output_schema is not None
    
    # Verify Coordinator Agent
    assert coordinator_agent.name == "coordinator_agent"
    assert coordinator_agent.model == "gemini-3.1-flash-lite"
    assert coordinator_agent.input_schema is not None
    assert coordinator_agent.output_schema is not None

    # Verify Vision Agent
    assert vision_agent.name == "vision_agent"
    assert vision_agent.model == "gemini-flash-latest"
    assert vision_agent.instruction is not None

    # Verify Awareness Agent
    assert awareness_agent.name == "awareness_agent"
    assert awareness_agent.model == "gemini-3.1-flash-lite"
    assert awareness_agent.instruction is not None
    assert awareness_agent.output_schema is not None
    
    print("All agents initialization tests passed successfully!")

if __name__ == "__main__":
    test_agents_initialization()
