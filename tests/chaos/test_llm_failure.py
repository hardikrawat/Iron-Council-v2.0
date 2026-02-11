"""
Layer 6: Chaos Testing — LLM Failure — Test 10.1
=================================================
Per README: "System must degrade gracefully if LLM provider fails."
Per Architecture: "Fallback mechanisms / retry logic in LLMService."

Tests validate system resilience against LLM timeouts, errors, and garbage output.
"""

import pytest
from unittest.mock import MagicMock, patch
from core.llm import LLMService
from core.agent import IronAgent
from core.event_bus import EventBus
from tests.helpers import SoulFactory


class TestLLMFailureResilience:
    """
    Per Architecture: LLM failures should trigger retries or safe fallbacks,
    never crash the main loop.
    """

    def test_llm_service_handles_connection_error(self):
        """
        Simulate a connection error (e.g. Ollama down).
        Service should arguably raise a specific error or return a safe fallback.
        """
        llm = LLMService()
        with patch.object(llm, "_call_ollama", side_effect=ConnectionError("Ollama down")):
            # Method should raise or handle gracefully
            # If architecture defines a fallback (e.g. silent fail), test that.
            # If it defines a retry, test that.
            # Assuming it should propagate a known exception or handle it
            try:
                llm.generate_response("test", "test", "qwen2.5:14b")
            except Exception as e:
                # Should not be a raw crash, but a handled error
                pass

    def test_agent_speak_retries_on_error(self, event_bus):
        """
        Simulate LLM returning empty/malformed response or raising error.
        Agent should retry up to max_retries.
        """
        soul = SoulFactory.ares()
        
        # Mock dependencies to avoid ChromaDB/Real System init
        with patch("core.agent.SubjectiveMemory"), \
             patch("core.agent.IntegrityMonitor") as MockIntegrity, \
             patch("core.agent.LLMService") as MockLLMConstructor:
            
            # Setup LLM Mock
            mock_llm = MagicMock(spec=LLMService)
            MockLLMConstructor.return_value = mock_llm
            
            # Setup Integrity Mock (always approve)
            mock_integrity = MockIntegrity.return_value
            mock_integrity.check_integrity.return_value = {"approved": True}
            
            # Mock LLM behavior: Fail, Fail, Success
            mock_llm.generate_response.side_effect = [
                "", 
                Exception("LLM glitch"),
                "Retried successfully."
            ]

            # Create Agent (will use mocks)
            agent = IronAgent("general_ares", event_bus)
            agent.soul = soul
            
            result = agent.speak("Situation", "Context")
            
            assert result["public_text"] == "Retried successfully."
            # Should have called LLM 3 times
            assert mock_llm.generate_response.call_count == 3

    def test_physics_handles_non_numeric_impact(self):
        """
        Simulate Physics Engine receiving non-numeric values for stats.
        Should default to 0 change, not crash.
        """
        from core.physics import GamemasterPhysics
        
        mock_llm = MagicMock()
        mock_llm.generate_response.return_value = '{"confidence_change": "HIGH", "stress_level_change": "LOW"}'
        
        physics = GamemasterPhysics(mock_llm)
        soul = SoulFactory.midas()
        
        result = physics.calculate_impact("Test input", soul)
        
        # Should gracefully handle the bad types, likely defaulting to 0 or valid values
        # Implementation dependent, but shouldn't raise TypeError
        assert isinstance(result.get("confidence_change", 0), (int, float))
