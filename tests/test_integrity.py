import sys
import os
import json
from unittest.mock import MagicMock

# Add project root and dummy keys
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
sys.path.append(os.getcwd())

from core.integrity import IntegrityMonitor
from core.llm import LLMService

def test_integrity_check():
    # Mock LLMService
    mock_llm = MagicMock(spec=LLMService)
    monitor = IntegrityMonitor(llm_service=mock_llm)
    
    # Mock AgentSoul
    mock_agent = MagicMock()
    mock_agent.name = "Ares"
    mock_agent.archetype = "Aggressive"
    mock_agent.dynamic_stats.confidence = 90
    mock_agent.dynamic_stats.paranoia = 20
    
    # Mock Success Response
    mock_llm.generate_response.return_value = json.dumps({
        "approved": False,
        "critique": "Ares is too arrogant to apologize.",
        "rewrite_suggestion": "Remove the 'sorry' part."
    })
    
    print("Testing integrity check...")
    result = monitor.check_integrity(mock_agent, "I am sorry for my mistake.")
    
    print(f"Result: {result}")
    assert result["approved"] is False
    assert "arrogant" in result["critique"]
    print("Integrity check OK")

    # Test Markdown cleaning
    mock_llm.generate_response.return_value = "```json\n{\"approved\": true, \"critique\": null, \"rewrite_suggestion\": null}\n```"
    result = monitor.check_integrity(mock_agent, "Victory is ours.")
    print(f"Result with markdown: {result}")
    assert result["approved"] is True
    print("Markdown cleaning OK")

if __name__ == "__main__":
    test_integrity_check()
