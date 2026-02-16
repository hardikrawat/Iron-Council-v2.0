import os
import logging
from typing import List
from memory.turso_store import TursoMemory

logger = logging.getLogger(__name__)


class SubjectiveMemory:
    def __init__(self, db_path: str = None, event_bus=None):
        """
        Initialize the TursoMemory backend.
        The db_path is currently ignored in favor of the Turso remote connection,
        consistent with replacing the failing local SQLite architecture.
        """
        self.event_bus = event_bus
        self.backend = TursoMemory(event_bus=event_bus)

    def save_memory(self, agent_name: str, text: str, emotion: str):
        """Saves a memory via the Turso backend."""
        self.backend.save_memory(agent_name, text, emotion)

    def recall_memories(
        self, agent_name: str, query: str, n_results: int = 3
    ) -> List[str]:
        """Recalls memories via the Turso backend."""
        return self.backend.recall_memories(agent_name, query, n_results)

    def get_last_dream(self, agent_name: str) -> str:
        """Retrieves the last dream via the Turso backend."""
        return self.backend.get_last_dream(agent_name)
