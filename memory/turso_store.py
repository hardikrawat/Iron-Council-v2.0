import os
import uuid
from datetime import datetime
from typing import List, Dict, Any
import logging
import libsql_client

import logging
import libsql_client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class TursoMemory:
    def __init__(self, event_bus=None):
        """
        Initialize a Turso (libSQL) client.
        URL and TOKEN are pulled from environment variables.
        """
        load_dotenv()
        self.event_bus = event_bus
        self.url = os.getenv("TURSO_DB_URL")
        self.token = os.getenv("TURSO_DB_TOKEN")

        # Fix: Turso client and some regions/proxies prefer https over libsql protocol
        if self.url and self.url.startswith("libsql://"):
            self.url = self.url.replace("libsql://", "https://")

        if not self.url or not self.token:
            logger.error(f"[TURSO] URL or Token missing. URL: {bool(self.url)}, Token: {bool(self.token)}")
            self.client = None
        else:
            try:
                logger.info(f"[TURSO] Connecting to {self.url}")
                self.client = libsql_client.create_client_sync(url=self.url, auth_token=self.token)
                self._init_db()
            except Exception as e:
                logger.error(f"[TURSO] Failed to connect to Turso: {e}")
                self.client = None

    def _init_db(self):
        """Creates the memories table if it doesn't exist."""
        if not self.client:
            return
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            agent_name TEXT,
            content TEXT,
            emotion TEXT,
            timestamp TEXT
        );
        """
        try:
            self.client.execute(create_table_sql)
            # Create an index for faster lookups
            self.client.execute("CREATE INDEX IF NOT EXISTS idx_agent_name ON memories(agent_name);")
            logger.info("[TURSO] Database initialized successfully.")
        except Exception as e:
            logger.error(f"[TURSO] Failed to initialize table: {e}")

    def save_memory(self, agent_name: str, text: str, emotion: str):
        """Saves a memory to the Turso DB."""
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(
                EventType.MEMORY_ACCESS, {"agent": agent_name, "op": "WRITE"}
            )

        if not self.client:
            logger.error(f"[TURSO] Client not initialized. Cannot save memory for {agent_name}.")
            return

        try:
            memory_id = str(uuid.uuid4())
            current_time = datetime.now().isoformat()
            
            insert_sql = "INSERT INTO memories (id, agent_name, content, emotion, timestamp) VALUES (?, ?, ?, ?, ?)"
            self.client.execute(insert_sql, (memory_id, agent_name, text, emotion, current_time))
            logger.debug(f"[TURSO] Memory saved for {agent_name}.")
        except Exception as e:
            logger.error(f"[TURSO] Failed to save memory for {agent_name}: {e}")

    def recall_memories(self, agent_name: str, query: str, n_results: int = 3) -> List[str]:
        """
        Recalls memories for an agent.
        Since remote vector search isn't native, we use a keyword-based search for now.
        For production, this would use a vector extension or a local embedding cache.
        """
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(
                EventType.MEMORY_ACCESS, {"agent": agent_name, "op": "READ"}
            )

        if not self.client:
            logger.error(f"[TURSO] Client not initialized. Cannot recall memories for {agent_name}.")
            return []

        try:
            # Simple keyword search fallback
            # We split the query into words and search for any matches
            # A more advanced version would use FTS5 if enabled in libSQL
            keywords = query.split()
            where_clause = "agent_name = ?"
            params = [agent_name]
            
            if keywords:
                keyword_clauses = " OR ".join(["content LIKE ?" for _ in keywords])
                where_clause += f" AND ({keyword_clauses})"
                params.extend([f"%{kw}%" for kw in keywords])

            select_sql = f"SELECT content, emotion, timestamp FROM memories WHERE {where_clause} ORDER BY timestamp DESC LIMIT ?"
            params.append(n_results)
            
            result_set = self.client.execute(select_sql, tuple(params))
            
            formatted_memories = []
            for row in result_set.rows:
                content, emotion, timestamp = row
                formatted = f"[{timestamp}] (Emotion: {emotion}) {content}"
                formatted_memories.append(formatted)

            return formatted_memories
        except Exception as e:
            logger.error(f"[TURSO] Failed to recall memories for {agent_name}: {e}")
            return []

    def get_last_dream(self, agent_name: str) -> str:
        """Retrieves the most recent dream (emotion='reflection') for the agent."""
        if not self.client:
            return ""

        try:
            select_sql = "SELECT content FROM memories WHERE agent_name = ? AND emotion = 'reflection' ORDER BY timestamp DESC LIMIT 1"
            result_set = self.client.execute(select_sql, (agent_name,))
            
            if result_set.rows:
                return result_set.rows[0][0]
        except Exception as e:
            logger.error(f"[TURSO] Failed to fetch last dream for {agent_name}: {e}")

        return ""

    def wipe_all(self):
        """Clears all memories from the database."""
        if not self.client:
            return
        
        try:
            self.client.execute("DELETE FROM memories")
            logger.info("[TURSO] All memories wiped.")
        except Exception as e:
            logger.error(f"[TURSO] Failed to wipe memories: {e}")
