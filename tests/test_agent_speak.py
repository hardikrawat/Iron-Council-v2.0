import sys
import os
import json
from unittest.mock import MagicMock, patch

# Add project root and dummy keys
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
sys.path.append(os.getcwd())

from core.agent import IronAgent

def test_agent_speak():
    # Mock LLMService and IntegrityMonitor
    with patch('core.agent.LLMService') as MockLLM, \
         patch('core.agent.IntegrityMonitor') as MockIntegrity:
        
        # Setup mocks
        mock_llm_instance = MockLLM.return_value
        mock_integ_instance = MockIntegrity.return_value
        
        # Scenario: Rejection then Rewrite
        agent = IronAgent("general_ares") # assuming this agent folder exists from previous conversations
        
        # Draft Response
        mock_llm_instance.generate_response.side_effect = [
            "I apologize for the delay.", # Draft 1
            "I will not tolerate delays. Move out!" # Final Rewrite
        ]
        
        # Integrity Check (Rejected)
        mock_integ_instance.check_integrity.return_value = {
            "approved": False,
            "critique": "General Ares is arrogant and never apologizes."
        }
        
        print("Testing agent speak with rejection...")
        response = agent.speak("The troops are waiting for orders.")
        
        print(f"Final Response: {response}")
        assert response == "I will not tolerate delays. Move out!"
        assert mock_llm_instance.generate_response.call_count == 2
        print("Rejection flow OK")

        # Scenario: Instant Approval
        mock_llm_instance.generate_response.side_effect = None
        mock_llm_instance.generate_response.return_value = "Proceed with caution."
        mock_integ_instance.check_integrity.return_value = {"approved": True}
        
        print("Testing agent speak with instant approval...")
        response = agent.speak("Intel reporting movement.")
        assert response == "Proceed with caution."
        print("Approval flow OK")

if __name__ == "__main__":
    try:
        test_agent_speak()
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
