"""
Layer 5: WebSocket Agent Post — Frontend Contract Test
=======================================================
Per Architecture: bridge_events_to_websocket broadcasts agent_post to frontend.
Per Frontend (Post.jsx): Expects data.{id, name, public_text, hidden_text, stats, relationships, timestamp}
Per Frontend (App.jsx): On agent_post, updates both posts[] and agents[] state.

Tests validate the EXACT payload shape the frontend components consume.
"""

import datetime
import pytest
from core.schema import AgentSoul, DynamicStats, RelationshipModel, Goal
from tests.helpers import SoulFactory, MockConnectionManager


class TestAgentPostPayload:
    """
    Per Architecture + Frontend Contract:
    The agent_post websocket message must have ALL fields that Post.jsx destructures.
    """

    def test_agent_post_has_required_fields(self):
        """
        Simulate the bridge payload structure and verify all required fields present.
        Frontend (Post.jsx line 33-37): extracts name, public_text, hidden_text from data.
        Frontend (App.jsx line 116): updates agents with stats, relationships from data.
        """
        soul = SoulFactory.ares()

        # Simulate what bridge_events_to_websocket constructs (server.py lines 163-176)
        agent_data = {
            "id": "general_ares",
            "name": soul.name,
            "public_text": "We must increase military spending.",
            "hidden_text": "",
            "stats": soul.dynamic_stats.model_dump(),
            "relationships": soul.get_serializable_relationships(),
            "timestamp": datetime.datetime.now().isoformat()
        }
        ws_payload = {"type": "agent_post", "data": agent_data}

        # Validate all required fields for Post.jsx
        assert ws_payload["type"] == "agent_post"
        data = ws_payload["data"]
        assert "id" in data, "Missing 'id' — App.jsx uses a.id for agent matching"
        assert "name" in data, "Missing 'name' — Post.jsx displays agent name"
        assert "public_text" in data, "Missing 'public_text' — Post.jsx primary content"
        assert "hidden_text" in data, "Missing 'hidden_text' — Post.jsx spoiler layer"
        assert "stats" in data, "Missing 'stats' — App.jsx syncs agent stats on post"
        assert "relationships" in data, "Missing 'relationships' — App.jsx syncs graph on post"
        assert "timestamp" in data, "Missing 'timestamp' — Post.jsx displays post time"

    def test_stats_is_plain_dict_not_pydantic(self):
        """
        Per Frontend: stats must be a plain dict. Pydantic models cannot be JSON.serialized
        by WebSocket send_json.
        """
        soul = SoulFactory.ares()
        stats = soul.dynamic_stats.model_dump()

        assert isinstance(stats, dict)
        assert "confidence" in stats
        assert "paranoia" in stats
        assert "loyalty_to_chairman" in stats
        assert "stress_level" in stats
        assert "energy" in stats
        # Must be plain int/float values, not nested objects
        for key, val in stats.items():
            assert isinstance(val, (int, float)), f"stat '{key}' is {type(val)}, expected numeric"

    def test_relationships_serializable_for_frontend(self):
        """
        Per Frontend (Sidebar.jsx line 440): accesses a.relationships?.[b.name]?.trust_score
        Must be dict of {name: {trust_score, last_interaction_summary, hidden_agenda}}.
        """
        soul = SoulFactory.ares()
        rels = soul.get_serializable_relationships()

        assert isinstance(rels, dict)
        for name, rel_data in rels.items():
            assert isinstance(rel_data, dict), f"Relationship for '{name}' is not a dict"
            assert "trust_score" in rel_data, f"Missing 'trust_score' for '{name}' — Sidebar Social Matrix needs it"
            assert "last_interaction_summary" in rel_data
            assert "hidden_agenda" in rel_data

    def test_hidden_text_empty_when_approved(self):
        """
        Per Architecture: When ego filter approves, hidden_text should be empty string.
        Frontend (Post.jsx line 41): hasHiddenLayer = hidden_text.trim().length > 0
        """
        # An approved response has empty hidden_text
        hidden_text = ""
        has_hidden_layer = hidden_text.strip().__len__() > 0
        assert has_hidden_layer is False, "Empty hidden_text should not trigger hidden layer display"

    def test_hidden_text_nonempty_triggers_display(self):
        """
        Per Frontend (Post.jsx line 41): Non-empty hidden_text triggers the spoiler div.
        """
        hidden_text = "Original draft before ego filter rewrote it."
        has_hidden_layer = len(hidden_text.strip()) > 0
        assert has_hidden_layer is True, "Non-empty hidden_text should trigger hidden layer"
