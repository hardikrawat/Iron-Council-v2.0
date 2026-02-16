import asyncio
import json
import logging
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from core.dream import _intelligent_json_recovery, dream_phase

# Setup logging
logging.basicConfig(level=logging.INFO)


def test_intelligent_json_recovery_plus_sign():
    """Test repair of illegal '+' signs in numbers."""
    text = '{"stat_updates": {"confidence": +10, "paranoia": -5}}'
    success, data, error = _intelligent_json_recovery(text)
    assert success is True
    assert data["stat_updates"]["confidence"] == 10
    assert data["stat_updates"]["paranoia"] == -5


def test_intelligent_json_recovery_unescaped_newlines():
    """Test repair of unescaped newlines in strings."""
    text = '{\n  "dream_narrative": "I saw a battlefield.\nIt was cold.",\n  "stat_updates": {}\n}'
    success, data, error = _intelligent_json_recovery(text)
    assert success is True
    assert "battlefield.\\nIt was cold" in json.dumps(data)


def test_intelligent_json_recovery_text_wrapper():
    """Test extraction of JSON from surrounding text."""
    text = 'Certainly! Here is the dream data:\n\n```json\n{"dream_narrative": "Peaceful.", "stat_updates": {"energy": 5}}\n```\nI hope this helps!'
    success, data, error = _intelligent_json_recovery(text)
    assert success is True
    assert data["dream_narrative"] == "Peaceful."


@pytest.mark.asyncio
async def test_dream_phase_retry_logic():
    """Verify that dream_phase retries on invalid JSON."""
    mock_agent = MagicMock()
    mock_agent.id = "test_agent"
    mock_agent.display_name = "Test Agent"
    mock_agent.soul.base_model = "test-model"
    mock_agent.event_bus = None

    # Mock LLM to return invalid JSON first, then valid JSON
    mock_agent.llm.generate_response.side_effect = [
        "Invalid JSON { oops }",  # Attempt 1
        '{"dream_narrative": "Success after retry", "stat_updates": {"confidence": 5}}',  # Attempt 2
    ]

    with (
        patch("core.dream._prepare_dream_prompts", return_value=("sys", "user")),
        patch(
            "core.dream._apply_dream_consequences",
            side_effect=lambda a, d: d["dream_narrative"],
        ),
    ):

        result = await dream_phase(mock_agent, [])

        assert result == "Success after retry"
        assert mock_agent.llm.generate_response.call_count == 2
        # Verify feedback was sent
        second_call_args = mock_agent.llm.generate_response.call_args_list[1]
        assert "FEEDBACK ON PREVIOUS ATTEMPT" in second_call_args.kwargs["user_message"]


if __name__ == "__main__":
    # Quick manual run
    test_intelligent_json_recovery_plus_sign()
    test_intelligent_json_recovery_unescaped_newlines()
    test_intelligent_json_recovery_text_wrapper()
    print("Heuristics tests passed!")

    # Run async test manually
    print("Running async retry logic test...")
    asyncio.run(test_dream_phase_retry_logic())
    print("Async retry logic test passed!")
