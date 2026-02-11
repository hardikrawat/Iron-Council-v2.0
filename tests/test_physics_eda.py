
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

from core.event_bus import EventBus, EventType
from core.physics import GamemasterPhysics
from core.physics_system import PhysicsSystem
from core.agent import IronAgent
from core.schema import AgentSoul, DynamicStats, Goal

class TestPhysicsEDA(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 1. Setup mocks
        self.mock_llm = MagicMock()
        self.physics = GamemasterPhysics(self.mock_llm)
        self.event_bus = EventBus()
        self.transcript = []
        
        # 2. Setup Agent
        self.agent = MagicMock(spec=IronAgent)
        self.agent.agent_name = "test_agent"
        self.agent.soul = MagicMock(spec=AgentSoul)
        self.agent.soul.name = "Test Soul"
        self.agent.soul.dynamic_stats = DynamicStats()
        self.agent.soul.goals = [Goal(description="Survive")]
        self.agent.soul.relationships = {} # Mock dict
        
        # Mock methods
        self.agent.soul.update_stat = MagicMock()
        self.agent.soul.update_goal_progress = MagicMock()
        self.agent.soul.update_relationship = MagicMock()
        self.agent.soul.get_relationship = MagicMock(return_value=None)
        self.agent.save_state = MagicMock()

        self.agents = [self.agent]

        # 3. Setup System under test
        self.physics_system = PhysicsSystem(
            event_bus=self.event_bus,
            physics=self.physics,
            agents=self.agents,
            transcript=self.transcript
        )
        await self.physics_system.start()

    async def test_world_event_triggers_impact(self):
        """
        Verify WORLD_EVENT calls calculate_impact and updates stats.
        """
        # Mock physics response
        self.physics.calculate_impact = MagicMock(return_value={
            "confidence_change": 5,
            "paranoia_change": 2,
            "loyalty_change": -1,
            "goal_updates": {}
        })

        # Act
        payload = {"content": "The Chairman smiles."}
        await self.event_bus.publish(EventType.WORLD_EVENT, payload)
        
        # Allow async tasks to run
        await asyncio.sleep(0.1)

        # Assert
        self.physics.calculate_impact.assert_called_once()
        self.agent.soul.update_stat.assert_any_call('confidence', 5)
        self.agent.soul.update_stat.assert_any_call('paranoia', 2)
        
        # Check transcript
        self.assertEqual(len(self.transcript), 1)
        self.assertEqual(self.transcript[0]['type'], 'user')

    async def test_agent_speak_triggers_relationship_update(self):
        """
        Verify AGENT_SPEAK calls calculate_relationship_update.
        """
        # Create a second agent to be the listener/speaker
        speaker = MagicMock(spec=IronAgent)
        speaker.agent_name = "speaker_agent"
        speaker.soul = MagicMock()
        speaker.soul.name = "Speaker Soul"
        
        # Add to system
        self.physics_system.agents.append(speaker)
        
        # Mock physics response
        self.physics.calculate_relationship_update = MagicMock(return_value=5)

        # Act
        payload = {"agent": "speaker_agent", "content": "I trust the Chairman."}
        await self.event_bus.publish(EventType.AGENT_SPEAK, payload)
        
        await asyncio.sleep(0.1)

        # Assert
        # Should be called for 'self.agent' (listener) reacting to 'speaker_agent'
        self.physics.calculate_relationship_update.assert_called()
        call_args = self.physics.calculate_relationship_update.call_args
        # Args: speaker_name, content, listener_agent
        self.assertEqual(call_args[0][0], "speaker_agent")
        self.assertEqual(call_args[0][2], self.agent) # Listener

        # Check transcript
        self.assertEqual(len(self.transcript), 1)
        self.assertEqual(self.transcript[0]['type'], 'agent_post')
        self.assertEqual(self.transcript[0]['data']['name'], "Speaker Soul")

    async def test_no_infinite_loop(self):
        """
        Guardrail: Ensure physics system does NOT publish new events.
        """
        # Spy on event bus publish
        with patch.object(self.event_bus, 'publish', wraps=self.event_bus.publish) as mock_publish:
            # Trigger event
            await self.event_bus.publish(EventType.WORLD_EVENT, {"content": "Test"})
            await asyncio.sleep(0.1)
            
            # Count calls. Should be 1 (the one we triggered).
            # PhysicsSystem should NOT have called publish.
            self.assertEqual(mock_publish.call_count, 1)

if __name__ == "__main__":
    unittest.main()
