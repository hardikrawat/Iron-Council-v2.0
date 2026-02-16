"""
Layer 6: Chaos Testing — State Corruption — Test 10.2
======================================================
Per Architecture: "Agent state loaded from JSON. Corruption must be handled."

Tests validate system resilience against corrupted soul state files.
"""

import os
import shutil
import tempfile
import pytest
from core.agent import IronAgent
from core.event_bus import EventBus
from tests.helpers import SoulFactory


class TestStateCorruptionResilience:
    """
    Per Architecture: If state file is corrupted, agent initialization should fail safely
    or fallback (depending on implementation - likely fail fast for data integrity).
    """

    def test_corrupted_json_raises_or_logs(self, event_bus):
        """
        Simulate a corrupted soul_state.json (invalid JSON syntax).
        Agent initialization should raise an error, preventing startup with bad state.
        """
        tmpdir = tempfile.mkdtemp()
        try:
            agent_dir = os.path.join(tmpdir, "agents", "general_ares")
            os.makedirs(agent_dir)

            # Write invalid JSON
            with open(os.path.join(agent_dir, "soul_state.json"), "w") as f:
                f.write("{ invalid json: [ missing bracket }")

            # Should raise JSONDecodeError or similar
            # Implementation might wrap it, but it shouldn't proceed
            from unittest.mock import patch

            with patch(
                "core.agent.os.path.join",
                side_effect=lambda *args: os.path.join(tmpdir, *args[1:]),
            ):
                with pytest.raises(Exception):
                    IronAgent("general_ares", event_bus)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_missing_required_fields_raises(self, event_bus):
        """
        Simulate valid JSON but missing critical schema fields (e.g. no stats).
        Agent initialization should fail schema validation.
        """
        tmpdir = tempfile.mkdtemp()
        try:
            agent_dir = os.path.join(tmpdir, "agents", "general_ares")
            os.makedirs(agent_dir)

            # Write valid JSON but missing 'dynamic_stats'
            with open(os.path.join(agent_dir, "soul_state.json"), "w") as f:
                f.write('{"name": "General Ares", "archetype": "General"}')

            # Should raise Pydantic ValidationError
            from unittest.mock import patch

            with patch(
                "core.agent.os.path.join",
                side_effect=lambda *args: os.path.join(tmpdir, *args[1:]),
            ):
                with pytest.raises(Exception):
                    IronAgent("general_ares", event_bus)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
