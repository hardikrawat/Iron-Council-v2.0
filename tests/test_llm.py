import sys
import os
from unittest.mock import MagicMock, patch

# Add project root and dummy keys
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
sys.path.append(os.getcwd())

from core.llm import LLMService

def test_routing():
    service = LLMService()
    
    # Mock OpenAI client
    mock_openai = MagicMock()
    service.openai_client = mock_openai
    mock_openai.chat.completions.create.return_value.choices[0].message.content = "OpenAI Response"
    
    # Mock Anthropic client
    mock_anthropic = MagicMock()
    service.anthropic_client = mock_anthropic
    mock_anthropic.messages.create.return_value.content[0].text = "Anthropic Response"
    
    # Test GPT routing
    print("Testing GPT routing...")
    res = service.generate_response("gpt-4", "sys", "user")
    assert res == "OpenAI Response"
    print("GPT routing OK")
    
    # Test Claude routing
    print("Testing Claude routing...")
    res = service.generate_response("claude-3-opus", "sys", "user")
    assert res == "Anthropic Response"
    print("Claude routing OK")
    
    # Test Fallback (Unknown model)
    print("Testing fallback for unknown model...")
    res = service.generate_response("unknown-model", "sys", "user")
    assert res == "OpenAI Response"
    print("Fallback OK")

    # Test Exception Fallback
    print("Testing exception fallback...")
    mock_openai.chat.completions.create.side_effect = Exception("API Down")
    # This should trigger _fallback_response which will also fail due to side_effect, 
    # but in a real scenario it might try a different model.
    # In our implementation, _fallback_response calls _generate_openai("gpt-3.5-turbo").
    try:
        res = service.generate_response("gpt-4", "sys", "user")
    except Exception:
        print("Caught expected final exception after fallback failed too")

if __name__ == "__main__":
    test_routing()
