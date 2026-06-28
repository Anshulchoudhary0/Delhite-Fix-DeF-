import asyncio
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

# pyrefly: ignore [missing-import]
from google.genai import types
# pyrefly: ignore [missing-import]
from google.adk.runners import Runner
# pyrefly: ignore [missing-import]
from google.adk.sessions import InMemorySessionService
from agents.coordinator_agent.agent import root_agent as coordinator_agent
from agents.translation_agent.agent import TranslationResult

# Mock the sub-agent responses
async def mock_run_agent_helper(agent, prompt_or_parts):
    if agent.name == "vision_agent":
        # Returns plain text description
        return "A large deep pothole on a paved road, filled with muddy water."
    elif agent.name == "translation_agent":
        # Returns structured TranslationResult
        original_text = ""
        if isinstance(prompt_or_parts, str):
            original_text = prompt_or_parts
        return TranslationResult(
            translated_text="There is a large pothole near my house in Najafgarh due to which two bikes have already fallen",
            original_text=original_text,
            original_language="hindi"
        )
    elif agent.name == "duplicate_check_agent":
        # Returns DuplicateCheckResult
        from agents.duplicate_check_agent.agent import DuplicateCheckResult
        return DuplicateCheckResult(is_duplicate=False, reason="No duplicate found.")
    elif agent.name == "classifier_agent":
        # Returns CivicIssueClassification
        from agents.classifier_agent.agent import CivicIssueClassification
        return CivicIssueClassification(
            category="pothole",
            department="MCD",
            urgency="high",
            reasoning="Pothole causing safety hazards."
        )
    elif agent.name == "drafting_agent":
        # Returns DraftedComplaint
        from agents.drafting_agent.agent import DraftedComplaint
        return DraftedComplaint(
            channel="MCD 311 App",
            draft_text="Formal complaint: Repair the pothole at Najafgarh."
        )
    elif agent.name == "verifier_agent":
        # Returns VerificationResult
        from agents.verifier_agent.agent import VerificationResult
        return VerificationResult(
            verified=True,
            feedback="",
            draft_text="Formal complaint: Repair the pothole at Najafgarh."
        )
    elif agent.name == "awareness_agent":
        from agents.awareness_agent.agent import AwarenessResult
        return AwarenessResult(
            environmental_impact="You have taken a real step toward reducing pollution. Open burning of garbage contributes to PM2.5 levels. Please use the DPCC helpline 1800-11-4000."
        )
    return None

async def mock_validate_report(text):
    # Always accept in mock tests
    return True, ""

@patch("agents.coordinator_agent.agent.run_agent_helper", side_effect=mock_run_agent_helper)
@patch("guardrail.validate_report", side_effect=mock_validate_report)
async def test_coordinator_flows(mock_val, mock_helper):
    runner = Runner(
        agent=coordinator_agent,
        app_name=coordinator_agent.name,
        session_service=InMemorySessionService()
    )

    # ----------------------------------------------------
    # Case 1: Plain English text, no image (Skip both)
    # ----------------------------------------------------
    print("\n--- Test Case 1: Plain English text input ---")
    session = await runner.session_service.create_session(app_name=coordinator_agent.name, user_id="test_1")
    payload = {
        "issue_description": "Water is leaking near Rohini Sector 15 metro station.",
        "location": "Rohini",
        "recent_reports": []
    }
    events = runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    )
    final_text = ""
    async for event in events:
        if event.content and event.content.role == "model" and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
            if text.strip():
                final_text = text
    details = await runner.session_service.get_session(app_name=coordinator_agent.name, user_id="test_1", session_id=session.id)
    output = None
    for e in details.events:
        if e.author == coordinator_agent.name and e.output:
            output = e.output
    
    assert output is not None
    assert output["original_text"] is None
    assert output["visual_evidence"] is None
    assert output["original_language"] == "english"
    assert "Original report" not in output["verified_complaint_text"]
    assert "Visual evidence" not in output["verified_complaint_text"]
    assert "Original complaint (Hindi):" not in final_text
    print("Pass: Case 1 correctly skipped both agents and generated normal output.")

    # ----------------------------------------------------
    # Case 2: Hindi text input (Triggers Translation)
    # ----------------------------------------------------
    print("\n--- Test Case 2: Hindi text input ---")
    session = await runner.session_service.create_session(app_name=coordinator_agent.name, user_id="test_2")
    payload = {
        "issue_description": "मेरे घर के पास नजफगढ़ में बड़ा गड्ढा है जिससे दो बाइक गिर चुकी हैं",
        "location": "Najafgarh",
        "recent_reports": []
    }
    events = runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    )
    final_text = ""
    async for event in events:
        if event.content and event.content.role == "model" and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
            if text.strip():
                final_text = text
    details = await runner.session_service.get_session(app_name=coordinator_agent.name, user_id="test_2", session_id=session.id)
    output = None
    for e in details.events:
        if e.author == coordinator_agent.name and e.output:
            output = e.output
            
    assert output is not None
    assert output["original_text"] == "मेरे घर के पास नजफगढ़ में बड़ा गड्ढा है जिससे दो बाइक गिर चुकी हैं"
    assert output["original_language"] == "hindi"
    assert "Original report (Hindi):" not in output["verified_complaint_text"]
    assert "Original complaint (Hindi): मेरे घर के पास नजफगढ़ में बड़ा गड्ढा है जिससे दो बाइक गिर चुकी हैं" in final_text
    print("Pass: Case 2 translated Hindi input and appended original text to complaint and bottom of markdown.")

    # ----------------------------------------------------
    # Case 3: Image input (Triggers Vision)
    # ----------------------------------------------------
    print("\n--- Test Case 3: Image input ---")
    # Write a dummy image file to use for image_path testing
    dummy_img = "dummy_test_image.jpg"
    with open(dummy_img, "wb") as f:
        f.write(b"fake image data")

    try:
        session = await runner.session_service.create_session(app_name=coordinator_agent.name, user_id="test_3")
        payload = {
            "image_path": dummy_img,
            "location": "Najafgarh",
            "recent_reports": []
        }
        events = runner.run_async(
            session_id=session.id,
            user_id=session.user_id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
        )
        final_text = ""
        async for event in events:
            if event.content and event.content.role == "model" and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
                if text.strip():
                    final_text = text
        details = await runner.session_service.get_session(app_name=coordinator_agent.name, user_id="test_3", session_id=session.id)
        output = None
        for e in details.events:
            if e.author == coordinator_agent.name and e.output:
                output = e.output

        assert output is not None
        assert output["visual_evidence"] == "A large deep pothole on a paved road, filled with muddy water."
        assert output["original_language"] == "english"
        assert "Visual evidence: A large deep pothole on a paved road, filled with muddy water." in output["verified_complaint_text"]
        assert "Original complaint (Hindi):" not in final_text
        print("Pass: Case 3 processed image upload and appended visual evidence description to complaint.")
    finally:
        if os.path.exists(dummy_img):
            os.remove(dummy_img)

    # ----------------------------------------------------
    # Case 4: Combined Image and Hindi input
    # ----------------------------------------------------
    print("\n--- Test Case 4: Combined Image and Hindi text input ---")
    dummy_img = "dummy_test_image.jpg"
    with open(dummy_img, "wb") as f:
        f.write(b"fake image data")

    try:
        session = await runner.session_service.create_session(app_name=coordinator_agent.name, user_id="test_4")
        # In this case, since vision_agent is called first, the image description is obtained, 
        # and then since that description is in English, translation is skipped.
        # But let's also test where the user content passes an image part + Hindi text!
        # (This is handled by our image check first, description replaces issue_description).
        payload = {
            "image_path": dummy_img,
            "issue_description": "मेरे घर के पास नजफगढ़ में बड़ा गड्ढा है",
            "location": "Najafgarh",
            "recent_reports": []
        }
        events = runner.run_async(
            session_id=session.id,
            user_id=session.user_id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
        )
        final_text = ""
        async for event in events:
            if event.content and event.content.role == "model" and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
                if text.strip():
                    final_text = text
        details = await runner.session_service.get_session(app_name=coordinator_agent.name, user_id="test_4", session_id=session.id)
        output = None
        for e in details.events:
            if e.author == coordinator_agent.name and e.output:
                output = e.output

        assert output is not None
        assert output["visual_evidence"] == "A large deep pothole on a paved road, filled with muddy water."
        assert "Visual evidence:" in output["verified_complaint_text"]
        print("Pass: Case 4 processed both successfully.")
    finally:
        if os.path.exists(dummy_img):
            os.remove(dummy_img)

if __name__ == "__main__":
    asyncio.run(test_coordinator_flows())
