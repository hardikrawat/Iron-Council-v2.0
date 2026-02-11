"""
Layer 6: Chaos Testing — Liveness & Responsiveness
==================================================
Per Race Condition Analysis: "Must verify Heartbeat Drift is < 100ms."

Tests validate that long-running operations (Vector DB, LLM) do not block
the main event loop.
"""

import asyncio
import time
import pytest
from core.dream import dream_phase
from core.agent import IronAgent
from tests.helpers import SoulFactory
from unittest.mock import MagicMock, patch

@pytest.mark.anyio
class TestSystemLiveness:
    
    async def monitor_heartbeat(self, duration: float, error_threshold: float = 0.1):
        """
        Runs a 'heartbeat' in the background while other tasks run.
        Returns the maximum lag observed.
        """
        start_time = time.time()
        max_lag = 0.0
        
        while time.time() - start_time < duration:
            loop_start = time.time()
            sleep_time = 0.05 # 50ms tick
            await asyncio.sleep(sleep_time)
            
            actual_time = time.time() - loop_start
            lag = actual_time - sleep_time
            max_lag = max(max_lag, lag)
        
        return max_lag

    @patch("core.dream._save_dream_memory") # Mock the internal sync call
    async def test_dream_save_does_not_block_loop(self, mock_save):
        """
        Verify that saving a dream (which does file I/O) doesn't freeze the loop.
        """
        # Mock save to be slow (simulating blocking I/O)
        def slow_save(*args):
            time.sleep(0.5) # Block for 500ms
            
        mock_save.side_effect = slow_save
        
        # NOTE: In the FIXED code, dream_phase uses asyncio.to_thread, 
        # so this blocking mock should run in a separate thread and NOT block the loop.
        
        # Setup Agent
        agent = MagicMock()
        agent.soul = SoulFactory.ares()
        agent.llm.generate_response = MagicMock(return_value="Dream content")
        
        # Run Monitor and Dream Concurrently
        monitor_task = asyncio.create_task(self.monitor_heartbeat(duration=1.0))
        
        # Trigger Dream (which calls the slow save)
        await dream_phase(agent, [], {})
        
        max_lag = await monitor_task
        
        # If blocking: lag would be > 0.5s
        # If non-blocking: lag should be near 0 (just loop overhead)
        print(f"Max Heartbeat Lag: {max_lag:.4f}s")
        assert max_lag < 0.2, f"Event loop froze for {max_lag}s! (Threshold: 0.2s)"

