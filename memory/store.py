import os
import chromadb
from chromadb.utils import embedding_functions
import uuid
from datetime import datetime
from typing import List

import logging

logger = logging.getLogger(__name__)

class SubjectiveMemory:
    def __init__(self, db_path: str = None, event_bus=None):
        """
        Initialize a persistent ChromaDB client and collection.
        FIX MAJ-10: Handles embedding model download/init failures.
        """
        self.event_bus = event_bus
        # FIX: Honor environment variable for testing/containerization
        if db_path is None:
            db_path = os.getenv("CHROMA_DB_PATH", "db/")
            
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Use the DefaultEmbeddingFunction (all-MiniLM-L6-v2)
        try:
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        except Exception as e:
            logger.error(f"[MEMORY] Failed to load embedding model: {e}. Memory features may be degraded.")
            self.embedding_fn = None
        
        # Create or get the collection
        self.collection = self.client.get_or_create_collection(
            name="agent_memories",
            embedding_function=self.embedding_fn
        )

    def save_memory(self, agent_name: str, text: str, emotion: str):
        """
        Add the text to the collection with metadata and a unique ID.
        FIX MAJ-10: Handles embedding/ChromaDB failures gracefully.
        """
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.MEMORY_ACCESS, {"agent": agent_name, "op": "WRITE"})

        try:
            memory_id = str(uuid.uuid4())
            current_time = datetime.now().isoformat()
            
            self.collection.add(
                documents=[text],
                metadatas=[{
                    "agent": agent_name,
                    "emotion": emotion,
                    "timestamp": current_time
                }],
                ids=[memory_id]
            )
        except Exception as e:
            logger.error(f"[MEMORY] Failed to save memory for {agent_name}: {e}")

    def recall_memories(self, agent_name: str, query: str, n_results: int = 3) -> List[str]:
        """
        Query the collection using the text query and filter by agent.
        FIX MAJ-10: Handles embedding/ChromaDB failures gracefully.
        """
        if self.event_bus:
            from core.event_bus import EventType
            self.event_bus.publish_threadsafe(EventType.MEMORY_ACCESS, {"agent": agent_name, "op": "READ"})

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"agent": agent_name}
            )
            
            # Return the list of documents found
            docs = results["documents"][0]
            metadatas = results["metadatas"][0]
            
            formatted_memories = []
            if docs:
                for i, doc in enumerate(docs):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    timestamp = meta.get("timestamp", "Unknown Time")
                    emotion = meta.get("emotion", "neutral")
                    
                    # FIX: Context Collapse - Prepend metadata so agent knows WHEN/HOW it happened
                    formatted = f"[{timestamp}] (Emotion: {emotion}) {doc}"
                    formatted_memories.append(formatted)
                    
                return formatted_memories
        except Exception as e:
            logger.error(f"[MEMORY] Failed to recall memories for {agent_name}: {e}")
        return []

    def get_last_dream(self, agent_name: str) -> str:
        """
        Retrieves the most recent dream (emotion="reflection") for the agent.
        Used for Morning Reflection.
        """
        try:
            # Fetch last 5 reflections to ensure we get the absolute latest
            # ChromaDB .get() returns results in ID order (insertion order typically), but not guaranteed.
            # We will fetch metadata and sort by timestamp.
            results = self.collection.get(
                where={"$and": [{"agent": {"$eq": agent_name}}, {"emotion": {"$eq": "reflection"}}]},
                limit=5,
                include=["documents", "metadatas"]
            )
            
            if not results["documents"]:
                return ""

            # Pair docs with metadata
            memories = []
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i]
                ts = meta.get("timestamp", "")
                memories.append({"text": doc, "ts": ts})

            # Sort by timestamp descending
            memories.sort(key=lambda x: x["ts"], reverse=True)
            
            if memories:
                return memories[0]["text"]
                
        except Exception as e:
            logger.error(f"[MEMORY] Failed to fetch last dream for {agent_name}: {e}")
        
        return ""
