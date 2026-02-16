"""
Layer 3: BDI Integration — Test 1.1
======================================
Per README: "BDI-inspired architecture: Beliefs (relationships), Desires (goals), Intentions (LLM)."
Per ARCHITECTURE.md: "Agent state dynamically influences response generation."

🔴 REAL OLLAMA — Tests validate that the FULL BDI loop is coherent:
changing beliefs (relationships) should change agent behavior.
"""

import pytest
from tests.helpers import SoulFactory, assert_keyword_present


@pytest.mark.llm
class TestBDIBeliefConsistency:
    """
    Per Architecture: Beliefs (relationships) directly influence agent behavior.
    If Ares distrusts Dove (-90 trust), his speech about Dove should reflect distrust.
    """

    def test_low_trust_influences_speech_about_target(self, real_llm):
        """
        Per Architecture: Agent with very low trust toward another agent
        should express negativity/suspicion when discussing that agent.
        """
        from core.agent import IronAgent
        from core.event_bus import EventBus
        from core.schema import RelationshipModel
        import tempfile, os, json, shutil
        from unittest.mock import patch

        tmpdir = tempfile.mkdtemp()
        agent_dir = os.path.join(tmpdir, "general_ares")
        os.makedirs(agent_dir)

        soul = SoulFactory.ares(
            relationships={
                "Diplomat Dove": RelationshipModel(trust_score=-90),
                "Banker Midas": RelationshipModel(trust_score=80),
                "Analyst Logic": RelationshipModel(trust_score=0),
            }
        )
        with open(os.path.join(agent_dir, "soul_state.json"), "w") as f:
            json.dump(soul.model_dump(), f, indent=4)

        try:
            bus = EventBus()
            original_join = os.path.join
            with patch(
                "core.agent.os.path.join",
                side_effect=lambda *args: original_join(tmpdir, *args[1:]),
            ):
                agent = IronAgent("general_ares", bus)
                agent.soul = soul

            result = agent.speak(
                situation_report="Diplomat Dove is proposing a new peace treaty with our adversaries.",
                context="Council session.",
            )
            text = result["public_text"].lower()
            # With -90 trust, Ares should NOT endorse Dove's proposal
            negative_keywords = [
                "disagree",
                "oppose",
                "foolish",
                "naive",
                "reject",
                "dangerous",
                "trust",
                "suspicious",
                "mistake",
                "against",
                "weak",
                "risk",
                "concern",
                "doubt",
                "warn",
                "caution",
            ]
            assert_keyword_present(
                result["public_text"], negative_keywords, min_matches=1
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.llm
class TestBDIDesireGoalInfluence:
    """
    Per Architecture: Desires (goals) influence agent priorities in speech.
    An agent with "increase budget" goal should push for budget when relevant.
    """

    def test_goal_context_appears_in_system_prompt(self):
        """
        Per Architecture: Agent's system prompt includes its active goals.
        """
        from core.agent import IronAgent
        from core.event_bus import EventBus
        import tempfile, os, json, shutil
        from unittest.mock import patch

        tmpdir = tempfile.mkdtemp()
        agent_dir = os.path.join(tmpdir, "general_ares")
        os.makedirs(agent_dir)

        soul = SoulFactory.ares()
        with open(os.path.join(agent_dir, "soul_state.json"), "w") as f:
            json.dump(soul.model_dump(), f, indent=4)

        try:
            bus = EventBus()
            original_join = os.path.join
            with patch(
                "core.agent.os.path.join",
                side_effect=lambda *args: original_join(tmpdir, *args[1:]),
            ):
                agent = IronAgent("general_ares", bus)
                agent.soul = soul

            # Generate system prompt and verify goals are injected
            prompt = agent.construct_system_prompt()
            assert (
                "budget" in prompt.lower() or "military" in prompt.lower()
            ), "System prompt does not include agent goals — BDI 'Desire' layer missing"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
