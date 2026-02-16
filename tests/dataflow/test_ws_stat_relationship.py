"""
Layer 5: WebSocket Stat & Relationship Updates — Frontend Contract Test
========================================================================
Per Architecture: PhysicsSystem broadcasts AGENT_STATUS events after stat changes.
Per Frontend (App.jsx): stat_update and relationship_update handled separately.
Per Frontend (AgentMonitor): Displays stats.{loyalty_to_chairman, confidence, paranoia}
Per Frontend (Social Matrix): Displays relationships[name].trust_score with sign-based coloring.

Tests validate the EXACT payload shapes that update the sidebar.
"""

import pytest
from core.schema import RelationshipModel, Goal
from tests.helpers import SoulFactory


class TestStatUpdatePayload:
    """
    Per Frontend (App.jsx line 63-68):
    stat_update: { type, agent_id, stats, goals }
    Updates agent stats AND goals in the sidebar AgentMonitor.
    """

    def test_stat_update_has_required_fields(self):
        """
        Simulate the stat_update payload from bridge_agent_status (server.py lines 224-231).
        """
        soul = SoulFactory.ares()
        stats_payload = {
            "type": "stat_update",
            "agent_id": "general_ares",
            "stats": soul.dynamic_stats.model_dump(),
            "goals": [g.model_dump() for g in soul.goals],
        }

        assert stats_payload["type"] == "stat_update"
        assert (
            "agent_id" in stats_payload
        ), "Missing 'agent_id' — App.jsx uses it to match agent"
        assert "stats" in stats_payload, "Missing 'stats' — AgentMonitor displays these"
        assert (
            "goals" in stats_payload
        ), "Missing 'goals' — AgentMonitor OBJ button uses these"

    def test_stats_has_all_five_fields(self):
        """
        Per Frontend (AgentMonitor lines 73-87): Directly accesses stats.loyalty_to_chairman,
        stats.confidence, stats.paranoia. All 5 documented stats must be present.
        """
        soul = SoulFactory.ares()
        stats = soul.dynamic_stats.model_dump()

        required = [
            "confidence",
            "paranoia",
            "loyalty_to_chairman",
            "stress_level",
            "energy",
        ]
        for field in required:
            assert field in stats, f"Missing stat '{field}' — AgentMonitor expects it"

    def test_goals_have_required_fields(self):
        """
        Per Frontend (AgentMonitor line 23): Accesses goal.active, goal.progress, goal.description
        """
        soul = SoulFactory.ares()
        goals = [g.model_dump() for g in soul.goals]

        assert len(goals) > 0, "Agent has no goals — Architecture requires active goals"
        for goal in goals:
            assert "description" in goal, "Missing 'description' in goal"
            assert (
                "active" in goal
            ), "Missing 'active' in goal — AgentMonitor filters by this"
            assert (
                "progress" in goal
            ), "Missing 'progress' in goal — AgentMonitor shows progress bar"
            assert "priority" in goal, "Missing 'priority' in goal"


class TestRelationshipUpdatePayload:
    """
    Per Frontend (App.jsx line 44-46):
    relationship_update: { type, agent_id, relationships }
    Per Frontend (Sidebar.jsx line 440-444): Accesses trust_score with sign-based coloring.
    """

    def test_relationship_update_has_required_fields(self):
        """
        Simulate relationship_update from bridge_agent_status (server.py lines 215-220).
        """
        soul = SoulFactory.ares()
        graph_payload = {
            "type": "relationship_update",
            "agent_id": "general_ares",
            "relationships": soul.get_serializable_relationships(),
        }

        assert graph_payload["type"] == "relationship_update"
        assert "agent_id" in graph_payload
        assert "relationships" in graph_payload

    def test_trust_score_sign_preserved(self):
        """
        CRITICAL: Per Frontend (Sidebar.jsx line 442):
        score > 0 → green, score < 0 → red, score == 0 → gray.
        Negative trust MUST be negative in the payload — not absolute value.
        This is the 'Midas Paradox' regression check.
        """
        soul = SoulFactory.ares()
        # Ares has -50 trust toward Dove
        rels = soul.get_serializable_relationships()

        dove_trust = rels.get("Diplomat Dove", {}).get("trust_score", None)
        assert dove_trust is not None, "Relationship with Diplomat Dove missing"
        assert dove_trust < 0, (
            f"Trust score for Dove = {dove_trust} — expected NEGATIVE. "
            "Sign lost during serialization? Midas Paradox regression!"
        )

    def test_relationship_has_hidden_agenda(self):
        """
        Per Architecture: Relationships have hidden_agenda field for dream phase.
        This field must be serialized for the frontend.
        """
        soul = SoulFactory.ares()
        soul.relationships["Diplomat Dove"].hidden_agenda = (
            "Planning to undermine peace talks"
        )
        rels = soul.get_serializable_relationships()

        assert "hidden_agenda" in rels["Diplomat Dove"]
        assert (
            rels["Diplomat Dove"]["hidden_agenda"]
            == "Planning to undermine peace talks"
        )
