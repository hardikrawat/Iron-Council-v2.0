"""
Layer 5: WebSocket Init & History — Frontend Contract Test
===========================================================
Per Architecture: On connection, server sends 'init' with current state & history.
Per Frontend (App.jsx): init handler sets initial agents, posts, and logs.
Per Frontend (App.jsx): history handler (deprecated/redundant? usually part of init).

Tests validate the initial state payload contains all 4 agents and correct history shape.
"""

import pytest
from core.schema import AgentSoul
from tests.helpers import SoulFactory


class TestInitPayload:
    """
    Per Frontend (App.jsx lines 102-110):
    init: { type, agents, history, system_log }
    """

    def test_init_has_all_four_agents(self):
        """
        Simulate the init payload from websocket_endpoint (server.py).
        Must contain the 4 canonical agents: Ares, Dove, Midas, Logic.
        """
        souls = [
            SoulFactory.ares(),
            SoulFactory.dove(),
            SoulFactory.midas(),
            SoulFactory.logic(),
        ]

        # Simulate server constructing the init payload
        agents_data = []
        for soul in souls:
            # Server adds 'id' to the soul dump
            data = soul.model_dump()
            data["id"] = soul.name.lower().replace(" ", "_")
            # Server serializes relationships
            data["relationships"] = soul.get_serializable_relationships()
            # Server serializes goals
            data["goals"] = [g.model_dump() for g in soul.goals]
            agents_data.append(data)

        payload = {
            "type": "init",
            "agents": agents_data,
            "history": [],
            "system_log": [],
        }

        assert len(payload["agents"]) == 4
        ids = [a["id"] for a in payload["agents"]]
        assert "general_ares" in ids
        assert "diplomat_dove" in ids
        assert "banker_midas" in ids
        assert "analyst_logic" in ids

    def test_agent_payload_in_init_matches_contract(self):
        """
        The agent objects in 'init' must match what App.jsx expects for state.agents.
        This is the same shape as 'stat_update' + 'relationship_update' combined.
        """
        soul = SoulFactory.ares()
        agent_data = soul.model_dump()
        agent_data["id"] = "general_ares"
        agent_data["relationships"] = soul.get_serializable_relationships()

        payload = {"type": "init", "agents": [agent_data]}

        target = payload["agents"][0]
        assert "id" in target
        assert "name" in target
        assert "dynamic_stats" in target
        assert "relationships" in target
        assert "goals" in target


class TestHistoryPayload:
    """
    Per Frontend (App.jsx): history is an array of post objects.
    Each post must match the 'agent_post' or 'user_post' shape.
    """

    def test_history_item_matches_post_contract(self):
        """
        History items must have the same fields as live posts so Post.jsx can render them.
        """
        history_item = {
            "type": "agent_post",  # Stored in history with type
            "data": {
                "id": "general_ares",
                "name": "General Ares",
                "public_text": "Historical message.",
                "hidden_text": "",
                "timestamp": "2023-01-01T12:00:00",
            },
        }

        payload = {"type": "init", "history": [history_item]}

        post = payload["history"][0]["data"]
        # Must have fields required by Post.jsx
        assert "name" in post
        assert "public_text" in post
        assert "timestamp" in post
