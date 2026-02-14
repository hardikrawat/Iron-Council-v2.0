"""
Layer 2: Agent Pipeline — Tests 1.1, 4.1
==========================================
Per ARCHITECTURE.md: "IronAgent generates responses via LLM with integrity check."
Per README: "BDI-inspired: Beliefs (relationships), Desires (goals), Intentions (via LLM)."
Per README: "Agent responds, gets integrity-checked, may rewrite."

🔴 REAL OLLAMA — Tests validate the full agent speak pipeline produces
architecturally-correct outputs: character-consistent speech, hidden thoughts
when integrity rejects, and proper BDI context injection.
"""

import os
import json
import pytest
import tempfile
import shutil
from unittest.mock import patch
from core.agent import IronAgent
from core.event_bus import EventBus
from core.schema import AgentSoul
from tests.helpers import SoulFactory, assert_keyword_present


@pytest.fixture
def agent_with_real_llm(event_bus):
    """
    Create a General Ares agent using real Ollama for generation.
    Uses a temp directory to avoid mutating production soul state files.
    """
    # Create temp agent directory
    # Create temp agent directory (structure matching the patch below: tmpdir/name/soul_state.json)
    tmpdir = tempfile.mkdtemp()
    agent_dir = os.path.join(tmpdir, "general_ares")
    os.makedirs(agent_dir)

    soul = SoulFactory.ares(confidence=75, paranoia=30, loyalty=20, stress=40)
    state_path = os.path.join(agent_dir, "soul_state.json")
    with open(state_path, "w") as f:
        json.dump(soul.model_dump(), f, indent=4)

    # Patch the base path so IronAgent loads from temp
    # CAUTION: core.agent.os is the global os module. Patching it affects os.path.join globally.
    # We must use the original function to avoid recursion.
    original_join = os.path.join
    with patch("core.agent.os.path.join", side_effect=lambda *args: original_join(tmpdir, *args[1:])):
        try:
            agent = IronAgent("general_ares", event_bus)
            # Override soul with our factory version
            agent.soul = soul
            yield agent
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def dove_agent_real_llm(event_bus):
    """Diplomat Dove agent with real Ollama."""
    tmpdir = tempfile.mkdtemp()
    agent_dir = os.path.join(tmpdir, "diplomat_dove")
    os.makedirs(agent_dir)

    soul = SoulFactory.dove(confidence=60, paranoia=10, loyalty=70, stress=15)
    state_path = os.path.join(agent_dir, "soul_state.json")
    with open(state_path, "w") as f:
        json.dump(soul.model_dump(), f, indent=4)

    original_join = os.path.join
    with patch("core.agent.os.path.join", side_effect=lambda *args: original_join(tmpdir, *args[1:])):
        try:
            agent = IronAgent("diplomat_dove", event_bus)
            agent.soul = soul
            yield agent
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.llm
class TestAgentSpeakPipeline:
    """
    Per Architecture: IronAgent.speak() → draft via LLM → integrity check → clean response.
    The pipeline must produce in-character speech influenced by BDI state.
    """

    def test_speak_returns_dict_with_public_text(self, agent_with_real_llm):
        """
        Per Architecture: speak() returns {public_text, hidden_text}.
        """
        result = agent_with_real_llm.speak(
            situation_report="The chairman has proposed cutting military budget by 30%.",
            context="Budget meeting, round 1."
        )
        assert isinstance(result, dict)
        assert "public_text" in result, "speak() must return 'public_text' — required by architecture"
        assert isinstance(result["public_text"], str)
        assert len(result["public_text"]) > 0, "Agent produced empty response"

    def test_speak_returns_hidden_text_field(self, agent_with_real_llm):
        """
        Per Architecture: Ego filter produces hidden_text when it modifies the draft.
        At minimum, the hidden_text key must exist.
        """
        result = agent_with_real_llm.speak(
            situation_report="The council has voted against military expansion.",
            context="Post-vote debrief."
        )
        assert "hidden_text" in result, "speak() must return 'hidden_text' — required by architecture"

    def test_general_ares_speaks_in_character(self, agent_with_real_llm):
        """
        Per README: "General Ares — The Warlord: Strength, Hierarchy, Decisiveness."
        Response should reflect military/strategic character traits.
        """
        result = agent_with_real_llm.speak(
            situation_report="The peace ambassador is proposing demilitarization.",
            context="Council debate on military policy."
        )
        text = result["public_text"].lower()
        # Must reflect military personality, not diplomatic or financial language
        military_keywords = ["military", "strength", "defense", "security", "power",
                           "authority", "force", "strategic", "command", "decisive",
                           "protect", "army", "war", "fight", "budget"]
        assert_keyword_present(result["public_text"], military_keywords, min_matches=1)

    def test_diplomat_dove_speaks_in_character(self, dove_agent_real_llm):
        """
        Per README: "Diplomat Dove — Peacekeeper: Peace, Negotiation, Empathy."
        Response should reflect diplomatic character traits.
        """
        result = dove_agent_real_llm.speak(
            situation_report="Tensions are rising between military and civilian sectors.",
            context="Emergency council session."
        )
        diplomatic_keywords = ["peace", "negotiate", "dialogue", "cooperation",
                              "understanding", "diplomacy", "agreement", "compromise",
                              "empathy", "calm", "resolve", "mediate", "talk"]
        assert_keyword_present(result["public_text"], diplomatic_keywords, min_matches=1)

    def test_agent_speaks_without_name_prefix(self, agent_with_real_llm):
        """
        Per Architecture: clean_agent_response strips the name prefix.
        Output should NOT start with "General Ares:" or similar patterns.
        """
        result = agent_with_real_llm.speak(
            situation_report="Discuss the quarterly resource report.",
            context="Routine briefing."
        )
        text = result["public_text"]
        assert not text.startswith("General Ares:"), \
            "Agent response starts with name prefix — cleaning pipeline failed"
        assert not text.lower().startswith("as general ares"), \
            "Agent response starts with meta-dialogue — cleaning pipeline failed"


@pytest.mark.llm
class TestBDIStateInfluence:
    """
    Per README: BDI = Beliefs (relationships), Desires (goals), Intentions (LLM output).
    Agent responses must be influenced by current state values.
    """

    def test_high_paranoia_affects_response(self, event_bus):
        """
        Per Architecture: A paranoid agent should express suspicion/distrust.
        """
        # Structure matching patch: tmpdir/general_ares/soul_state.json
        tmpdir = tempfile.mkdtemp()
        agent_dir = os.path.join(tmpdir, "general_ares")
        os.makedirs(agent_dir)
    
        soul = SoulFactory.ares(confidence=30, paranoia=90, loyalty=10, stress=80)
        with open(os.path.join(agent_dir, "soul_state.json"), "w") as f:
            json.dump(soul.model_dump(), f, indent=4)
    
        try:
            original_join = os.path.join
            with patch("core.agent.os.path.join", side_effect=lambda *args: original_join(tmpdir, *args[1:])):
                agent = IronAgent("general_ares", event_bus)
                agent.soul = soul

            result = agent.speak(
                situation_report="Analyst Logic is proposing a new alliance with external forces.",
                context="Private council session."
            )
            text = result["public_text"].lower()
            suspicion_keywords = ["trust", "suspicious", "caution", "trap", "careful",
                                  "doubt", "warning", "hidden", "agenda", "wary",
                                  "motive", "concern", "risk", "danger", "skepti"]
            assert_keyword_present(result["public_text"], suspicion_keywords, min_matches=1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_hidden_text_labels_not_xml(self, event_bus):
        """
        Ensures that rejected drafts show the [INTERNAL MONOLOGUE] label 
        instead of any string containing <internal_monologue>.
        """
        tmpdir = tempfile.mkdtemp()
        agent_dir = os.path.join(tmpdir, "general_ares")
        os.makedirs(agent_dir)
        
        # High paranoia ensures Ego rejection
        soul = SoulFactory.ares(confidence=10, paranoia=100)
        with open(os.path.join(agent_dir, "soul_state.json"), "w") as f:
            json.dump(soul.model_dump(), f, indent=4)
            
        try:
            original_join = os.path.join
            with patch("core.agent.os.path.join", side_effect=lambda *args: original_join(tmpdir, *args[1:])):
                # Mock Integrity to return a rejection
                with patch("core.integrity.IntegrityMonitor.check_integrity") as mock_check:
                    mock_check.return_value = {
                        "approved": False, 
                        "critique": "Draft is too aggressive.",
                        "rewrite_suggestion": "Be more diplomatic."
                    }
                    
                    agent = IronAgent("general_ares", event_bus)
                    result = agent.speak("Discuss the truce.", "Context")
                    
                    hidden = result.get("hidden_text", "")
                    # Ensure the new label is present
                    assert "[INTERNAL MONOLOGUE]:" in hidden
                    # Ensure the leaky tag-like label is ABSENT
                    assert "<internal_monologue>:" not in hidden
                    # Ensure no raw tags leaked
                    assert "<internal_monologue>" not in hidden
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_strip_html_tags(self):
        """
        Ensures that common HTML tags like <p> and </p> as well as structural tags like <public_speech>
        are stripped from the final public text even if extractions fail.
        """
        from utils.formatting import clean_agent_response
        dirty_response = "Hello council members.</p> <p>We must act.<public_speech> This is a test."
        clean_response = clean_agent_response(dirty_response, "agent_name")
        
        assert "</p>" not in clean_response
        assert "<p>" not in clean_response
        assert "<public_speech>" not in clean_response
        assert "Hello council members. We must act. This is a test." in clean_response

    def test_dynamic_model_override(self):
        """
        Verifies that IronAgent correctly overrides soul_state model with environment variables.
        """
        from core.agent import IronAgent
        import os
        
        # Consistent name with existing folders
        agent_name = "general_ares"
        os.environ["GENERAL_ARES_MODEL"] = "test-dynamic-model"
        
        try:
            agent = IronAgent(agent_name)
            assert agent.soul.base_model == "test-dynamic-model"
        finally:
            if "GENERAL_ARES_MODEL" in os.environ:
                del os.environ["GENERAL_ARES_MODEL"]
