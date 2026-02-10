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


# --- BASIC STAT CHANGE TESTS (User ↔ Agent ONLY) ---

def test_calculate_impact_success(physics, mock_llm_service):
    mock_llm_service.generate_response.return_value = '{"confidence_change": 5, "paranoia_change": -2, "loyalty_change": 10, "reasoning": "The Chairman showed great support.", "goal_updates": {}}'
    
    result = physics.calculate_impact("General Ares", {"confidence": 50}, "I fully support you, Ares.")
    
    assert result["confidence_change"] == 5
    assert result["paranoia_change"] == -2
    assert result["loyalty_change"] == 10
    assert result["reasoning"] == "The Chairman showed great support."
    assert result["goal_updates"] == {}

def test_calculate_impact_with_markdown_markers(physics, mock_llm_service):
    mock_llm_service.generate_response.return_value = '```json\n{"confidence_change": -10, "paranoia_change": 5, "loyalty_change": -5, "reasoning": "Threatening behavior detected.", "goal_updates": {}}\n```'
    
    result = physics.calculate_impact("General Ares", {}, "I will replace you if you fail.")
    
    assert result["confidence_change"] == -10

def test_calculate_impact_no_relationship_changes(physics, mock_llm_service):
    """calculate_impact should NOT produce relationship_changes — that's reconcile_turn's job."""
    mock_llm_service.generate_response.return_value = '{"confidence_change": 5, "paranoia_change": 0, "loyalty_change": 0, "reasoning": "Support.", "goal_updates": {}}'
    
    result = physics.calculate_impact("General Ares", {}, "Support Ares.")
    
    # relationship_changes should exist as empty dict (legacy compat)
    assert result["relationship_changes"] == {}

def test_calculate_impact_prompt_excludes_agent_context(physics, mock_llm_service):
    """Verify the prompt does NOT mention other agents — domain separation."""
    mock_llm_service.generate_response.return_value = '{"confidence_change": 0, "paranoia_change": 0, "loyalty_change": 0, "reasoning": "Neutral", "goal_updates": {}}'
    
    physics.calculate_impact("General Ares", {}, "Discuss strategy.")
    
    args, kwargs = mock_llm_service.generate_response.call_args
    prompt = kwargs["user_message"]
    assert "Other agents spoke" not in prompt
    assert "ONLY consider the Chairman" in prompt


# --- GOAL UPDATE TESTS ---

def test_calculate_impact_with_goal_updates(physics, mock_llm_service):
    mock_llm_service.generate_response.return_value = '{"confidence_change": 5, "paranoia_change": 0, "loyalty_change": 0, "reasoning": "Budget talk helped.", "goal_updates": {"military budget": 15, "peace initiative": -5}}'
    
    result = physics.calculate_impact(
        "General Ares", {}, "Let's increase military spending.",
        agent_goals=["Secure military budget increase", "Undermine Dove's peace initiative"]
    )
    
    assert result["goal_updates"]["military budget"] == 15
    assert result["goal_updates"]["peace initiative"] == -5


# --- ERROR HANDLING TESTS ---

def test_calculate_impact_json_error(physics, mock_llm_service):
    mock_llm_service.generate_response.return_value = 'Invalid JSON response'
    
    result = physics.calculate_impact("General Ares", {}, "Confusion.")
    
    assert result["confidence_change"] == 0
    assert result["relationship_changes"] == {}
    assert result["goal_updates"] == {}
    assert "Error parsing" in result["reasoning"]

def test_calculate_impact_with_plus_sign(physics, mock_llm_service):
    mock_llm_service.generate_response.return_value = '{ "confidence_change": +5, "paranoia_change": +2, "loyalty_change": -10, "reasoning": "Test", "goal_updates": {} }'
    
    result = physics.calculate_impact("General Ares", {}, "Test action")
    
    assert result["confidence_change"] == 5
    assert result["paranoia_change"] == 2

def test_calculate_impact_general_exception(physics, mock_llm_service):
    mock_llm_service.generate_response.side_effect = Exception("API Link Down")
    
    result = physics.calculate_impact("General Ares", {}, "Action")
    
    assert result["confidence_change"] == 0
    assert result["relationship_changes"] == {}
    assert result["goal_updates"] == {}
    assert "System error" in result["reasoning"]

def test_missing_fields_default_to_empty(physics, mock_llm_service):
    """LLM might omit goal_updates — should default to empty dict."""
    mock_llm_service.generate_response.return_value = '{"confidence_change": 3, "paranoia_change": 0, "loyalty_change": 0, "reasoning": "Minimal response"}'
    
    result = physics.calculate_impact("General Ares", {}, "Hello")
    
    assert result["relationship_changes"] == {}
    assert result["goal_updates"] == {}


# --- RECONCILIATION TESTS (Agent ↔ Agent ONLY) ---

def test_reconcile_turn_basic(physics, mock_llm_service):
    """Test basic trust matrix generation from agent responses."""
    mock_llm_service.generate_response.return_value = '{"General Ares": {"Diplomat Dove": -15, "Analyst Logic": 10}, "Diplomat Dove": {"General Ares": -20, "Analyst Logic": 5}, "Analyst Logic": {"General Ares": 15, "Diplomat Dove": -10}}'
    
    responses = [
        {"name": "General Ares", "public_text": "Dove is incompetent and must be removed."},
        {"name": "Diplomat Dove", "public_text": "Ares endangers our people with reckless violence."},
        {"name": "Analyst Logic", "public_text": "General Ares has the expertise for a surgical strike."}
    ]
    core_values = {
        "General Ares": ["military strength", "decisive action"],
        "Diplomat Dove": ["peace", "diplomacy"],
        "Analyst Logic": ["data transparency", "efficiency"]
    }
    
    result = physics.reconcile_turn(responses, core_values)
    
    assert result["General Ares"]["Diplomat Dove"] == -15
    assert result["General Ares"]["Analyst Logic"] == 10
    assert result["Analyst Logic"]["General Ares"] == 15

def test_reconcile_turn_prompt_contains_values(physics, mock_llm_service):
    """Verify the reconciliation prompt includes agent core values and semantic alignment rules."""
    mock_llm_service.generate_response.return_value = '{"Agent A": {"Agent B": 5}, "Agent B": {"Agent A": -5}}'
    
    responses = [
        {"name": "Agent A", "public_text": "I support the plan."},
        {"name": "Agent B", "public_text": "The plan is reckless."}
    ]
    core_values = {
        "Agent A": ["unity", "strength"],
        "Agent B": ["caution", "analysis"]
    }
    
    physics.reconcile_turn(responses, core_values)
    
    args, kwargs = mock_llm_service.generate_response.call_args
    prompt = kwargs["user_message"]
    assert "Semantic Alignment" in prompt.upper() or "SEMANTIC ALIGNMENT" in prompt
    assert "sarcasm" in prompt.lower() or "SARCASM" in prompt
    assert "unity" in prompt
    assert "caution" in prompt

def test_reconcile_turn_filters_self_references(physics, mock_llm_service):
    """Self-trust entries should be silently removed."""
    mock_llm_service.generate_response.return_value = '{"Agent A": {"Agent A": 99, "Agent B": 10}, "Agent B": {"Agent A": -5, "Agent B": 50}}'
    
    responses = [
        {"name": "Agent A", "public_text": "Hello"},
        {"name": "Agent B", "public_text": "World"}
    ]
    
    result = physics.reconcile_turn(responses, {})
    
    assert "Agent A" not in result.get("Agent A", {})
    assert "Agent B" not in result.get("Agent B", {})
    assert result["Agent A"]["Agent B"] == 10
    assert result["Agent B"]["Agent A"] == -5

def test_reconcile_turn_single_agent_returns_empty(physics, mock_llm_service):
    """Only 1 agent spoke — nothing to reconcile."""
    result = physics.reconcile_turn(
        [{"name": "Solo", "public_text": "Monologue."}], {}
    )
    assert result == {}

def test_reconcile_turn_json_error(physics, mock_llm_service):
    """Bad JSON from LLM should return empty dict, not crash."""
    mock_llm_service.generate_response.return_value = 'Not valid JSON at all'
    
    responses = [
        {"name": "A", "public_text": "Hi"},
        {"name": "B", "public_text": "Hello"}
    ]
    
    result = physics.reconcile_turn(responses, {})
    assert result == {}

def test_reconcile_turn_exception(physics, mock_llm_service):
    """Generic exception should return empty dict, not crash."""
    mock_llm_service.generate_response.side_effect = Exception("Network error")
    
    responses = [
        {"name": "A", "public_text": "Hi"},
        {"name": "B", "public_text": "Hello"}
    ]
    
    result = physics.reconcile_turn(responses, {})
    assert result == {}

def test_reconcile_turn_with_plus_signs(physics, mock_llm_service):
    """Plus signs in JSON should be cleaned."""
    mock_llm_service.generate_response.return_value = '{"Ares": {"Dove": +15}, "Dove": {"Ares": -10}}'
    
    responses = [
        {"name": "Ares", "public_text": "Good work Dove."},
        {"name": "Dove", "public_text": "Ares is too aggressive."}
    ]
    
    result = physics.reconcile_turn(responses, {})
    assert result["Ares"]["Dove"] == 15
    assert result["Dove"]["Ares"] == -10
