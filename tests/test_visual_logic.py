
import sys
import unittest
from unittest.mock import MagicMock

# MOCK CHROMADB BEFORE IMPORTING ANYTHING ELSE
sys.modules["chromadb"] = MagicMock()
sys.modules["chromadb.utils"] = MagicMock()
sys.modules["chromadb.utils.embedding_functions"] = MagicMock()

# Mock memory.store to avoid importing the real one which imports chromadb
mock_store_module = MagicMock()
sys.modules["memory.store"] = mock_store_module

import os
# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Now import server
from server import VisualIronAgent, IntegritySpy

class TestVisualAgent(unittest.TestCase):
    def setUp(self):
        # Patch the internal components of IronAgent
        # IronAgent.__init__ calls self._load_soul(), LLMService(), IntegrityMonitor(), SubjectiveMemory()
        
        # We need to mock IronAgent completely or patch its init
        self.original_init = VisualIronAgent.__init__
        
    def test_spy_capture(self):
        # Create a mock integrity monitor
        original_integrity = MagicMock()
        original_integrity.check_integrity.return_value = {"approved": False, "critique": "Too bland."}
        
        # Create spy
        spy = IntegritySpy(original_integrity)
        
        # Test capture
        draft = "Hidden Draft"
        soul = MagicMock()
        spy.check_integrity(soul, draft)
        
        self.assertEqual(spy.last_draft, "Hidden Draft")
        original_integrity.check_integrity.assert_called_with(soul, draft)

if __name__ == "__main__":
    unittest.main()
