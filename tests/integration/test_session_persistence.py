"""
Layer 3: Session Persistence — Test 8.1
=========================================
Per ARCHITECTURE.md: "Agent Soul persisted as JSON files."
Per README: "Session state saved and restorable across server restarts."

Tests validate state save/restore integrity for agents and session logs.
"""

import os
import json
import tempfile
import shutil
import pytest
from core.schema import AgentSoul
from tests.helpers import SoulFactory


class TestAgentStatePersistence:
    """
    Per Architecture: Agent soul state is persisted as a JSON file.
    Changes to stats, relationships, and goals must survive save+restore.
    """

    def test_soul_save_and_restore(self):
        """Per Architecture: Soul state roundtrips through JSON file."""
        tmpdir = tempfile.mkdtemp()
        try:
            soul = SoulFactory.ares(confidence=73, paranoia=41, stress=55)
            soul.update_relationship("Diplomat Dove", -25, "Disagreed on budget")
            soul.update_goal_progress("military budget", 35)

            path = os.path.join(tmpdir, "soul_state.json")
            with open(path, "w") as f:
                f.write(soul.model_dump_json(indent=4))

            with open(path, "r") as f:
                restored = AgentSoul.model_validate_json(f.read())

            assert restored.dynamic_stats.confidence == 73
            assert restored.dynamic_stats.paranoia == 41
            assert restored.dynamic_stats.stress_level == 55
            assert (
                restored.relationships["Diplomat Dove"].trust_score == -75
            )  # -50 + -25
            assert (
                "budget"
                in restored.relationships[
                    "Diplomat Dove"
                ].last_interaction_summary.lower()
            )
            assert restored.goals[0].progress == 35
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_persistence_preserves_negative_trust(self):
        """
        CRITICAL: Negative trust scores must survive persistence.
        The 'Midas Paradox' bug previously lost negative signs.
        """
        tmpdir = tempfile.mkdtemp()
        try:
            soul = SoulFactory.ares()
            soul.update_relationship("Diplomat Dove", -30)  # Should be -80 total

            path = os.path.join(tmpdir, "soul_state.json")
            with open(path, "w") as f:
                f.write(soul.model_dump_json(indent=4))

            with open(path, "r") as f:
                restored = AgentSoul.model_validate_json(f.read())

            assert (
                restored.relationships["Diplomat Dove"].trust_score < 0
            ), "Negative trust score lost during persistence — Midas Paradox regression!"
            assert restored.relationships["Diplomat Dove"].trust_score == -80
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestSessionLogPersistence:
    """
    Per Architecture: Session transcript saved as JSON for dream phase input.
    """

    def test_session_log_save_and_restore(self):
        """Per Architecture: Session log is a JSON array that survives save/restore."""
        tmpdir = tempfile.mkdtemp()
        try:
            log = [
                {
                    "speaker": "Chairman",
                    "content": "Begin the session.",
                    "type": "user",
                },
                {
                    "speaker": "General Ares",
                    "content": "Ready for action.",
                    "type": "agent_post",
                    "data": {
                        "id": "general_ares",
                        "name": "General Ares",
                        "public_text": "Ready.",
                    },
                },
            ]
            path = os.path.join(tmpdir, "visual_session.json")
            with open(path, "w") as f:
                json.dump(log, f, indent=2)

            with open(path, "r") as f:
                restored = json.load(f)

            assert len(restored) == 2
            assert restored[0]["speaker"] == "Chairman"
            assert restored[1]["speaker"] == "General Ares"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_all_four_agent_souls_loadable(self):
        """
        Per Architecture: All four agent soul state files must be valid JSON.
        Tests against actual production files.
        """
        agents_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
            "agents",
        )
        expected_agents = [
            "general_ares",
            "diplomat_dove",
            "banker_midas",
            "analyst_logic",
        ]

        for agent_name in expected_agents:
            soul_path = os.path.join(agents_dir, agent_name, "soul_state.json")
            assert os.path.exists(
                soul_path
            ), f"Soul state file missing for {agent_name}"

            with open(soul_path, "r") as f:
                data = json.load(f)

            # Validate it parses as a valid AgentSoul
            soul = AgentSoul.model_validate(data)
            assert soul.name, f"Agent {agent_name} has no name"
            assert soul.archetype, f"Agent {agent_name} has no archetype"
            assert soul.core_values, f"Agent {agent_name} has no core_values"
            assert soul.base_model, f"Agent {agent_name} has no base_model"
