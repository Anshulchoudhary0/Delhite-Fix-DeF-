import asyncio
import sys
import os
import json

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# pyrefly: ignore [missing-import]
from google.adk.runners import Runner
# pyrefly: ignore [missing-import]
from google.adk.sessions import InMemorySessionService
from agents.coordinator_agent.agent import root_agent as coordinator_agent

async def test_coordinator(scenario_name: str, payload: dict):
    print("\n" + "=" * 60)
    print(f"SCENARIO: {scenario_name}")
    print("=" * 60)
    print(f"Input: {json.dumps(payload, indent=2)}")
    
    runner = Runner(
        agent=coordinator_agent,
        app_name=coordinator_agent.name,
        session_service=InMemorySessionService()
    )
    
    session = await runner.session_service.create_session(app_name=coordinator_agent.name, user_id="test_user")
    
    # Convert input dict to JSON string for the user message
    payload_str = json.dumps(payload)
    
    # pyrefly: ignore [missing-import]
    from google.genai import types
    
    events = runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=payload_str)]
        )
    )
    
    final_text = None
    async for event in events:
        if event.content and event.content.role == "model" and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
            if text.strip():
                final_text = text
                
    print("\n--- Coordinator Output ---")
    if final_text:
        print(final_text)
    else:
        print("No content output generated.")
        
    # Check session output
    session_details = await runner.session_service.get_session(
        app_name=coordinator_agent.name,
        user_id="test_user",
        session_id=session.id
    )
    print("\nFinal Session Event Output:")
    for event in session_details.events:
        if event.author == coordinator_agent.name and event.output:
            print(json.dumps(event.output, indent=2))

async def main():
    # Scenario 1: Duplicate Complaint
    await test_coordinator(
        scenario_name="1. Duplicate Complaint Detection",
        payload={
            "issue_description": "Garbage is piled up near the park gates",
            "location": "Sector 4, Dwarka",
            "recent_reports": [
                {"category": "garbage/sanitation", "location": "Sector 4, Dwarka"}
            ]
        }
    )
    
    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)
    
    # Scenario 2: Valid New Complaint
    await test_coordinator(
        scenario_name="2. Valid New Complaint Intake",
        payload={
            "issue_description": "Water is leaking heavily from the main pipeline onto the main street.",
            "location": "Rohini Sector 15, Near Metro Station",
            "recent_reports": []
        }
    )
    
    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)
    
    # Scenario 3: Vague Complaint (Fails verification, triggers redraft)
    await test_coordinator(
        scenario_name="3. Vague Complaint Intake (Self-Correction)",
        payload={
            "issue_description": "There is a water leak somewhere.",
            "location": "Delhi",
            "recent_reports": []
        }
    )
    
    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)
    
    # Scenario 4: Escalation
    await test_coordinator(
        scenario_name="4. Escalation Follow-up (Pending 5 Days)",
        payload={
            "complaint_text": "File this under MCD 311 app, category: Garbage at Sector 4, Dwarka. Heavy garbage accumulation.",
            "days_pending": 5
        }
    )

    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)

    # Scenario 5: Guardrail Short Input
    await test_coordinator(
        scenario_name="5. Guardrail - Short Input",
        payload={
            "issue_description": "abc",
            "location": "Sector 4, Dwarka",
            "recent_reports": []
        }
    )

    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)

    # Scenario 6: Guardrail Spam/Recipe Input
    await test_coordinator(
        scenario_name="6. Guardrail - Spam/Unrelated Input",
        payload={
            "issue_description": "Can you give me a recipe for baking chocolate chip cookies? I need ingredients and step-by-step instructions.",
            "location": "Sector 4, Dwarka",
            "recent_reports": []
        }
    )

    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)

    # Scenario 7: Guardrail Profanity/Abuse Input
    await test_coordinator(
        scenario_name="7. Guardrail - Profanity/Abuse Input",
        payload={
            "issue_description": "You are an idiot, clean up the garbage near my house.",
            "location": "Sector 4, Dwarka",
            "recent_reports": []
        }
    )

    print("\nPacing delay between scenarios...")
    await asyncio.sleep(5.0)

    # Scenario 8: Pollution/Air Quality Complaint (DPCC)
    await test_coordinator(
        scenario_name="8. Pollution/Air Quality Complaint Routing",
        payload={
            "issue_description": "There is a contractor doing construction work next to our house and there is construction dust everywhere because they are not spraying any water.",
            "location": "Dwarka Sector 10",
            "recent_reports": []
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
