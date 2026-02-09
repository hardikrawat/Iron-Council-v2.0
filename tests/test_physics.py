import pytest
from unittest.mock import MagicMock
from core.physics import GamemasterPhysics
from core.llm import LLMService

@pytest.fixture
def mock_llm_service():
    return MagicMock(spec=LLMService)

@pytest.fixture
def physics(mock_llm_service):
    return GamemasterPhysics(mock_llm_service)

def test_calculate_impact_success(physics, mock_llm_service):
    # Setup mock response
    mock_llm_service.generate_response.return_value = '{"confidence_change": 5, "paranoia_change": -2, "loyalty_change": 10, "reasoning": "The Chairman showed great support."}'
    
    agent_name = "General Ares"
    current_stats = {"confidence": 50, "paranoia": 10, "loyalty_to_chairman": 50}
    user_action = "I fully support your strategic initiative, Ares."
    
    result = physics.calculate_impact(agent_name, current_stats, user_action)
    
    assert result["confidence_change"] == 5
    assert result["paranoia_change"] == -2
    assert result["loyalty_change"] == 10
    assert result["reasoning"] == "The Chairman showed great support."
    
    # Verify mock was called with correct arguments
    mock_llm_service.generate_response.assert_called_once()
    args, kwargs = mock_llm_service.generate_response.call_args
    assert kwargs["model_name"] == "gpt-4o"
    assert agent_name in kwargs["user_message"]
    assert user_action in kwargs["user_message"]

def test_calculate_impact_with_markdown_markers(physics, mock_llm_service):
    # Setup mock response with markdown markers
    mock_llm_service.generate_response.return_value = '```json\n{"confidence_change": -10, "paranoia_change": 5, "loyalty_change": -5, "reasoning": "Threatening behavior detected."}\n```'
    
    result = physics.calculate_impact("General Ares", {}, "I will replace you if you fail.")
    
    assert result["confidence_change"] == -10
    assert result["reasoning"] == "Threatening behavior detected."

def test_calculate_impact_json_error(physics, mock_llm_service):
    # Setup mock response with invalid JSON
    mock_llm_service.generate_response.return_value = 'Invalid JSON response'
    
    result = physics.calculate_impact("General Ares", {}, "Confusion.")
    
    assert result["confidence_change"] == 0
    assert "Error parsing" in result["reasoning"]

def test_calculate_impact_with_plus_sign(physics, mock_llm_service):
    # Setup mock response with explicit + signs (invalid JSON but handled by our regex)
    mock_llm_service.generate_response.return_value = '{ "confidence_change": +5, "paranoia_change": +2, "loyalty_change": -10, "reasoning": "Test positive sign" }'
    
    result = physics.calculate_impact("General Ares", {}, "Test action")
    
    assert result["confidence_change"] == 5
    assert result["paranoia_change"] == 2
    assert result["loyalty_change"] == -10
    assert result["reasoning"] == "Test positive sign"

def test_calculate_impact_general_exception(physics, mock_llm_service):
    # Setup mock to raise an exception
    mock_llm_service.generate_response.side_effect = Exception("API Link Down")
    
    result = physics.calculate_impact("General Ares", {}, "Action")
    
    assert result["confidence_change"] == 0
    assert "System error" in result["reasoning"]
