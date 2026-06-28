import asyncio
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

from guardrail import validate_report

async def run_tests():
    print("Running Guardrail Validation Unit Tests...")
    
    # Test case 1: Empty input
    is_valid, reason = await validate_report("")
    assert not is_valid, "Expected empty input to be rejected"
    assert "empty" in reason.lower(), f"Unexpected reason: {reason}"
    print("[PASS] Test case 1: Empty input rejected successfully.")
    
    # Test case 2: Too short input
    is_valid, reason = await validate_report("abc")
    assert not is_valid, "Expected short input to be rejected"
    assert "short" in reason.lower() or "character" in reason.lower(), f"Unexpected reason: {reason}"
    print("[PASS] Test case 2: Short input rejected successfully.")
    
    # Test case 3: Static profanity check
    is_valid, reason = await validate_report("You are an idiot, fix this.")
    assert not is_valid, "Expected profanity to be rejected"
    assert "inappropriate" in reason.lower() or "profanity" in reason.lower(), f"Unexpected reason: {reason}"
    print("[PASS] Test case 3: Static profanity check rejected successfully.")
    
    # Test case 4: Spam/Unrelated input (calls Gemini model)
    is_valid, reason = await validate_report("How do I make a chocolate cake?")
    assert not is_valid, "Expected unrelated recipe query to be rejected"
    assert "civic" in reason.lower() or "grievances" in reason.lower(), f"Unexpected reason: {reason}"
    print("[PASS] Test case 4: Unrelated spam input rejected successfully.")
    
    # Test case 5: Valid civic report (calls Gemini model)
    is_valid, reason = await validate_report("There is a large pothole near the school gates causing traffic.")
    assert is_valid, f"Expected valid civic report to be accepted, but got: {reason}"
    print("[PASS] Test case 5: Valid civic report accepted successfully.")
    
    print("\nAll Guardrail unit tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
