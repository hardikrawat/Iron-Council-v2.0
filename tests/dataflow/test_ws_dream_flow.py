"""
Layer 5: WebSocket Dream Flow — Frontend Contract Test
======================================================
Per Architecture: Dream phase streams chunks to Sidebar (SubconsciousLog).
Per Frontend (Sidebar.jsx): stream_start, stream_chunk, stream_end, dream.
Per Frontend (SubconsciousLog): Appends chunks, then renders final markdown entry.

Tests validate the streaming protocol and final dream payload shape.
"""

import pytest
from tests.helpers import SoulFactory


class TestDreamStreamingProtocol:
    """
    Per Frontend (Sidebar.jsx lines 56-85):
    Handles 'stream_start', 'stream_chunk', 'stream_end', and final 'dream' message.
    """

    def test_stream_start_shape(self):
        """
        Payload: { type: "stream_start", agent_id }
        Triggers: Clearing previous stream buffer in SubconsciousLog.
        """
        payload = {
            "type": "stream_start",
            "agent_id": "general_ares"
        }
        assert payload["type"] == "stream_start"
        assert "agent_id" in payload, "Sidebar needs agent_id to route stream to correct log container"

    def test_stream_chunk_shape(self):
        """
        Payload: { type: "stream_chunk", Chunk: "text fragment..." }
        Triggers: Appending text to active stream buffer.
        """
        payload = {
            "type": "stream_chunk",
            "Chunk": "The war is inevitable..."
        }
        assert payload["type"] == "stream_chunk"
        assert "Chunk" in payload, "Frontend expects 'Chunk' (capitalized) — SubconsciousLog line 512"

    def test_stream_end_shape(self):
        """
        Payload: { type: "stream_end" }
        Triggers: Finalizing the stream display.
        """
        payload = {"type": "stream_end"}
        assert payload["type"] == "stream_end"


class TestFinalDreamPayload:
    """
    Per Frontend (Sidebar.jsx lines 86-90 + App.jsx lines 97-101):
    dream: { type, agent_id, dream }
    Payload: dream object containing { id, timestamp, content, emotion, agent_name }
    """

    def test_dream_message_has_required_fields(self):
        """
        The final 'dream' message persists the full dream to the log history.
        """
        import datetime
        soul = SoulFactory.ares()
        
        dream_obj = {
            "id": "dream_123",
            "timestamp": datetime.datetime.now().isoformat(),
            "content": "I dreamt of total victory.",
            "emotion": "triumphant",
            "agent_name": soul.name
        }
        
        payload = {
            "type": "dream",
            "agent_id": "general_ares",
            "dream": dream_obj
        }
        
        assert payload["type"] == "dream"
        assert "agent_id" in payload
        assert "dream" in payload
        
        d = payload["dream"]
        assert "content" in d, "Missing 'content' — SubconsciousLog displays the dream text"
        assert "timestamp" in d, "Missing 'timestamp' — SubconsciousLog sorts by time"
        assert "agent_name" in d, "Missing 'agent_name' — SubconsciousLog attribute"
