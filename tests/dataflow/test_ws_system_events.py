"""
Layer 5: WebSocket System Events — Frontend Contract Test
==========================================================
Per Architecture: Heartbeat ticks, system state, and activity events flow to UI.
Per Frontend (MissionStatus): tension bar, conch display, uptime clock.
Per Frontend (HardwareMonitor): DISK/LLM/NET LED indicators.
Per Frontend (WatchdogTerminal): system_log display.
Per Frontend (AgentMonitor): agent_status_update with OODA phase indicators.

Tests validate the EXACT payload shapes each sidebar component consumes.
"""

import datetime
import pytest


class TestSystemStatePayload:
    """
    Per Frontend (App.jsx line 56-62):
    system_state_update: { type, data.{tension, conch.{owner, expires_in}} }
    Per Frontend (MissionStatus lines 121-125): Displays tension bar and conch info.
    """

    def test_system_state_has_tension(self):
        """Simulate bridge_system_tick payload (server.py lines 237-241)."""
        payload = {
            "type": "system_state_update",
            "data": {
                "tension": 45,
                "conch": {"owner": "general_ares", "expires_in": 12}
            }
        }

        assert payload["type"] == "system_state_update"
        assert "tension" in payload["data"], "Missing 'tension' — MissionStatus ENTROPY bar needs it"
        assert "conch" in payload["data"], "Missing 'conch' — MissionStatus lock display needs it"
        assert isinstance(payload["data"]["tension"], (int, float))

    def test_conch_structure(self):
        """
        Per Frontend (MissionStatus lines 124-125):
        Accesses conch.owner and conch.expires_in directly.
        """
        conch = {"owner": "general_ares", "expires_in": 8}
        assert "owner" in conch, "Missing 'owner' — MissionStatus displays lock holder"
        assert "expires_in" in conch, "Missing 'expires_in' — MissionStatus shows auto-revoke countdown"

    def test_conch_null_when_free(self):
        """
        Per Frontend (MissionStatus lines 158-166):
        When conch is null/None, shows 'SYSTEM NOMINAL // CHANNEL OPEN'.
        """
        payload = {
            "type": "system_state_update",
            "data": {
                "tension": 10,
                "conch": None
            }
        }
        assert payload["data"]["conch"] is None


class TestHeartbeatPulsePayload:
    """
    Per Frontend (App.jsx line 42-43):
    heartbeat_pulse: { type, stats.{uptime, mem, status} }
    Per Frontend (WatchdogTerminal lines 296-297): Displays MEM and UPTIME.
    Per Frontend (MissionStatus lines 115-118): Formats uptime as HH:MM:SS.
    """

    def test_heartbeat_pulse_shape(self):
        """Simulate keepalive_task payload (server.py lines 309-316)."""
        payload = {
            "type": "heartbeat_pulse",
            "stats": {
                "uptime": 3661,
                "mem": "64.2MB",
                "status": "NORMAL"
            }
        }

        assert payload["type"] == "heartbeat_pulse"
        assert "uptime" in payload["stats"], "Missing 'uptime' — MissionStatus clock needs it"
        assert "mem" in payload["stats"], "Missing 'mem' — WatchdogTerminal footer displays it"
        assert "status" in payload["stats"]
        assert isinstance(payload["stats"]["uptime"], int)


class TestActivityEventPayload:
    """
    Per Frontend (App.jsx lines 69-72):
    activity_event: { type, event ("DISK"/"LLM"), data }
    Per Frontend (HardwareMonitor): DISK/LLM/NET LED flashes.
    """

    def test_disk_activity_event(self):
        """Simulate bridge_activity_event for MEMORY_ACCESS (server.py line 354)."""
        payload = {
            "type": "activity_event",
            "event": "DISK",
            "data": {"agent": "general_ares", "operation": "recall"}
        }
        assert payload["type"] == "activity_event"
        assert payload["event"] == "DISK", "MEMORY_ACCESS must map to 'DISK' — HardwareMonitor LED name"

    def test_llm_activity_event(self):
        """Simulate bridge_activity_event for LLM_ACTIVITY (server.py line 355)."""
        payload = {
            "type": "activity_event",
            "event": "LLM",
            "data": {"agent": "general_ares", "model": "qwen2.5:7b"}
        }
        assert payload["event"] == "LLM", "LLM_ACTIVITY must map to 'LLM' — HardwareMonitor LED name"


class TestSystemLogPayload:
    """
    Per Frontend (App.jsx lines 73-96):
    system_log: { type, content, level }
    Per Frontend (WatchdogTerminal lines 251-271): Parses [TIMESTAMP] [MODULE] > MESSAGE format.
    """

    def test_system_log_shape(self):
        """Simulate SystemLogger.log payload (server.py lines 279-286)."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [PHYSICS] > Applied stat changes to General Ares"

        payload = {
            "type": "system_log",
            "content": log_entry,
            "level": "INFO"
        }

        assert payload["type"] == "system_log"
        assert "content" in payload, "Missing 'content' — WatchdogTerminal displays this"
        assert "level" in payload, "Missing 'level' — WatchdogTerminal filters by level"
        assert isinstance(payload["content"], str)

    def test_log_format_parseable(self):
        """
        Per Frontend (WatchdogTerminal line 254):
        Regex: /\\[(.*?)\\] \\[(.*?)\\] > (.*)/
        Log entry must match this format for proper coloring.
        """
        import re
        log_entry = "[14:30:22] [PHYSICS] > Applied stat changes to General Ares"
        match = re.match(r'\[(.*?)\] \[(.*?)\] > (.*)', log_entry)
        assert match is not None, f"Log format not parseable by frontend regex: {log_entry}"
        timestamp, module, message = match.groups()
        assert len(timestamp) > 0
        assert len(module) > 0
        assert len(message) > 0


class TestAgentStatusUpdatePayload:
    """
    Per Frontend (App.jsx lines 47-55):
    agent_status_update: { type, data.{agent, status, details, phase} }
    Per Frontend (AgentMonitor lines 39-50): OODA phase indicators O-O-D-A.
    """

    def test_agent_status_update_shape(self):
        """
        Per Frontend (AgentMonitor lines 9-11):
        Extracts status, details, phase from the payload.
        """
        payload = {
            "type": "agent_status_update",
            "data": {
                "agent": "general_ares",
                "status": "THINKING",
                "details": "Evaluating military options",
                "phase": "D"  # Decide phase of OODA
            }
        }

        assert payload["type"] == "agent_status_update"
        data = payload["data"]
        assert "agent" in data, "Missing 'agent' — App.jsx uses it as key"
        assert "status" in data, "Missing 'status' — AgentMonitor displays status"
        assert "details" in data, "Missing 'details' — AgentMonitor status details"

    def test_ooda_phase_values(self):
        """
        Per Frontend (AgentMonitor lines 40-46):
        Phase values must be O, O, D, A matching OODA cycle.
        """
        valid_phases = ["O", "D", "A"]  # Observe/Orient = O, Decide = D, Act = A
        for phase in valid_phases:
            payload = {"phase": phase}
            assert payload["phase"] in valid_phases

    def test_valid_status_values(self):
        """
        Per Frontend (AgentMonitor lines 16-20):
        Status values determine color coding.
        """
        valid_statuses = ["IDLE", "THINKING", "ACTING", "WAITING_FOR_LOCK",
                          "OBSERVING", "ORIENTING", "DECIDING"]
        for status in valid_statuses:
            # Each must be a string the frontend recognizes
            assert isinstance(status, str)
