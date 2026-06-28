import asyncio
import sys
import os
import json

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

async def run_scenario_test(scenario_name: str, payload: dict) -> dict:
    runner = Runner(
        agent=coordinator_agent,
        app_name=coordinator_agent.name,
        session_service=InMemorySessionService()
    )
    
    session = await runner.session_service.create_session(app_name=coordinator_agent.name, user_id="test_runner")
    
    payload_str = json.dumps(payload)
    events = runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=payload_str)]
        )
    )
    
    final_text = ""
    async for event in events:
        if event.content and event.content.role == "model" and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
            if text.strip():
                final_text = text
                
    session_details = await runner.session_service.get_session(
        app_name=coordinator_agent.name,
        user_id="test_runner",
        session_id=session.id
    )
    
    output = None
    for event in session_details.events:
        if event.author == coordinator_agent.name and event.output:
            output = event.output
            
    return {
        "output": output,
        "markdown": final_text
    }

async def run_all_tests():
    # Reconfigure stdout to use UTF-8 on Windows to prevent console printing crashes
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("RUNNING SCENARIO TESTS FOR HINDI/HINGLISH/PHOTO PIPELINE")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Test A: Hindi input
    # -------------------------------------------------------------------------
    print("\n[TEST A] Hindi Input Test...")
    payload_a = {
        "issue_description": "नजफगढ़ में मेरे घर के पास सड़क पर बड़ा गड्ढा है, 2 हफ्ते से है",
        "location": "Najafgarh",
        "recent_reports": []
    }
    
    try:
        res_a = await run_scenario_test("Test A (Hindi)", payload_a)
        output_a = res_a["output"]
        markdown_a = res_a["markdown"]
        
        print("\n--- TEST A RAW RESULT SCHEMA ---")
        print(json.dumps(output_a, indent=2, ensure_ascii=False))
        print("\n--- TEST A MARKDOWN OUTPUT ---")
        print(markdown_a)
        
        # Verify expectations
        assert output_a is not None, "Test A: Output is empty"
        assert output_a["original_language"] in ("hindi", "hinglish"), f"Expected hindi or hinglish, got {output_a['original_language']}"
        assert output_a["original_text"] == "नजफगढ़ में मेरे घर के पास सड़क पर बड़ा गड्ढा है, 2 हफ्ते से है"
        assert "MCD" in output_a["department"].upper(), f"Expected MCD department, got {output_a['department']}"
        assert "Original complaint (Hindi):" in markdown_a
        
        print(">>> Test A: [PASS]")
    except Exception as e:
        print(f">>> Test A: [FAIL] - Error: {e}")

    # -------------------------------------------------------------------------
    # Test B: Hinglish input
    # -------------------------------------------------------------------------
    print("\n" + "-" * 50)
    print("[TEST B] Hinglish Input Test...")
    payload_b = {
        "issue_description": "Najafgarh mein mere ghar ke paas pothole hai bhai, bahut bada hai",
        "location": "Najafgarh",
        "recent_reports": []
    }
    
    try:
        res_b = await run_scenario_test("Test B (Hinglish)", payload_b)
        output_b = res_b["output"]
        markdown_b = res_b["markdown"]
        
        print("\n--- TEST B RAW RESULT SCHEMA ---")
        print(json.dumps(output_b, indent=2, ensure_ascii=False))
        print("\n--- TEST B MARKDOWN OUTPUT ---")
        print(markdown_b)
        
        # Verify expectations
        assert output_b is not None, "Test B: Output is empty"
        assert output_b["original_language"] == "hinglish", f"Expected hinglish, got {output_b['original_language']}"
        assert output_b["original_text"] == "Najafgarh mein mere ghar ke paas pothole hai bhai, bahut bada hai"
        assert "MCD" in output_b["department"].upper(), f"Expected MCD department, got {output_b['department']}"
        assert "Original complaint (Hindi):" in markdown_b
        
        print(">>> Test B: [PASS]")
    except Exception as e:
        print(f">>> Test B: [FAIL] - Error: {e}")

    # -------------------------------------------------------------------------
    # Test C: Photo simulation
    # -------------------------------------------------------------------------
    print("\n" + "-" * 50)
    print("[TEST C] Photo Simulation Test...")
    payload_c = {
        "issue_description": "[PHOTO INPUT]: dark, pothole approximately 3 feet wide on a paved road surface, edges cracked and crumbling, standing water visible inside",
        "location": "Najafgarh",
        "recent_reports": []
    }
    
    try:
        res_c = await run_scenario_test("Test C (Photo Simulation)", payload_c)
        output_c = res_c["output"]
        markdown_c = res_c["markdown"]
        
        print("\n--- TEST C RAW RESULT SCHEMA ---")
        print(json.dumps(output_c, indent=2, ensure_ascii=False))
        print("\n--- TEST C MARKDOWN OUTPUT ---")
        print(markdown_c)
        
        # Verify expectations
        assert output_c is not None, "Test C: Output is empty"
        assert output_c["visual_evidence"] == "dark, pothole approximately 3 feet wide on a paved road surface, edges cracked and crumbling, standing water visible inside"
        # Make sure the drafting agent included the Evidence section in the text
        assert "Photographic documentation shows" in output_c["verified_complaint_text"]
        
        print(">>> Test C: [PASS]")
    except Exception as e:
        print(f">>> Test C: [FAIL] - Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
