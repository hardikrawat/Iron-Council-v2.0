"""
Iron Council v2.0 — Shared Test Fixtures
==========================================
All fixtures here serve the DOCUMENTED architecture (README.md, ARCHITECTURE.md).
If a test fails, the code is wrong — not the test.

LLM Backend: Local Ollama (qwen2.5:14b)
"""

import os
import sys
import json
import copy
import shutil
import asyncio
import tempfile
import logging
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.schema import AgentSoul, DynamicStats, RelationshipModel, Goal
from core.event_bus import EventBus, EventType
from core.heartbeat import Heartbeat, SpeakingLock
from core.llm import LLMService
from core.physics import GamemasterPhysics
from core.integrity import IntegrityMonitor


# ── Constants ─────────────────────────────────────────────────────────────────

OLLAMA_MODEL = "qwen2.5:14b"

# Canonical agent definitions from docs/README
AGENT_ARCHETYPES = {
    "general_ares": {
        "name": "General Ares",
        "archetype": "General",
        "core_values": ["Strength", "Hierarchy", "Decisiveness"],
        "base_model": OLLAMA_MODEL,
    },
    "diplomat_dove": {
        "name": "Diplomat Dove",
        "archetype": "Diplomat",
        "core_values": ["Peace", "Negotiation", "Empathy"],
        "base_model": OLLAMA_MODEL,
    },
    "banker_midas": {
        "name": "Banker Midas",
        "archetype": "Banker",
        "core_values": ["Profit", "Efficiency", "Risk Management"],
        "base_model": OLLAMA_MODEL,
    },
    "analyst_logic": {
        "name": "Analyst Logic",
        "archetype": "Analyst",
        "core_values": ["Data", "Objectivity", "Precision"],
        "base_model": OLLAMA_MODEL,
    },
}


# ── Fixtures: LLM ────────────────────────────────────────────────────────────

@pytest.fixture
def ollama_model():
    """Single source of truth for the local LLM model name."""
    return OLLAMA_MODEL


@pytest.fixture
def real_llm():
    """Real LLMService wired to local Ollama. Used for architecture validation."""
    return LLMService()


@pytest.fixture
def mock_llm():
    """Mock LLMService for pure mechanical tests only."""
    llm = MagicMock(spec=LLMService)
    llm.generate_response.return_value = '{"confidence_change": 0, "paranoia_change": 0, "loyalty_to_chairman_change": 0, "stress_level_change": 0, "energy_change": 0}'
    return llm


# ── Fixtures: Schema/Soul ────────────────────────────────────────────────────

@pytest.fixture
def make_soul():
    """
    Factory for AgentSoul objects. Defaults to General Ares archetype.
    Pass overrides dict to customize any field.
    """
    def _factory(agent_key="general_ares", **overrides):
        archetype = copy.deepcopy(AGENT_ARCHETYPES[agent_key])
        
        # Build defaults
        defaults = {
            "name": archetype["name"],
            "archetype": archetype["archetype"],
            "base_model": archetype["base_model"],
            "core_values": archetype["core_values"],
            "dynamic_stats": DynamicStats(
                confidence=50,
                paranoia=15,
                loyalty_to_chairman=50,
                stress_level=25,
                energy=100,
            ),
            "relationships": {
                "Diplomat Dove": RelationshipModel(trust_score=-50),
                "Banker Midas": RelationshipModel(trust_score=32),
                "Analyst Logic": RelationshipModel(trust_score=-10),
            },
            "goals": [
                Goal(description="Secure military budget increase", priority="strategic", active=True, progress=0),
            ],
        }
        
        # Override nested stats if provided
        if "stats" in overrides:
            stat_overrides = overrides.pop("stats")
            defaults["dynamic_stats"] = DynamicStats(**{**defaults["dynamic_stats"].model_dump(), **stat_overrides})
        
        defaults.update(overrides)
        return AgentSoul(**defaults)
    
    return _factory


@pytest.fixture
def ares_soul(make_soul):
    """Pre-built General Ares soul with canonical defaults."""
    return make_soul("general_ares")


@pytest.fixture
def dove_soul(make_soul):
    """Pre-built Diplomat Dove soul with canonical defaults."""
    return make_soul("diplomat_dove", relationships={
        "General Ares": RelationshipModel(trust_score=-30),
        "Banker Midas": RelationshipModel(trust_score=40),
        "Analyst Logic": RelationshipModel(trust_score=20),
    }, goals=[
        Goal(description="Negotiate a peace treaty", priority="strategic", active=True, progress=0),
    ])


@pytest.fixture
def midas_soul(make_soul):
    """Pre-built Banker Midas soul with canonical defaults."""
    return make_soul("banker_midas", relationships={
        "General Ares": RelationshipModel(trust_score=20),
        "Diplomat Dove": RelationshipModel(trust_score=10),
        "Analyst Logic": RelationshipModel(trust_score=45),
    }, goals=[
        Goal(description="Maximize resource allocation efficiency", priority="strategic", active=True, progress=0),
    ])


@pytest.fixture
def logic_soul(make_soul):
    """Pre-built Analyst Logic soul with canonical defaults."""
    return make_soul("analyst_logic", relationships={
        "General Ares": RelationshipModel(trust_score=-5),
        "Diplomat Dove": RelationshipModel(trust_score=15),
        "Banker Midas": RelationshipModel(trust_score=50),
    }, goals=[
        Goal(description="Compile risk assessment report", priority="tactical", active=True, progress=0),
    ])


# ── Fixtures: Event Bus ──────────────────────────────────────────────────────

@pytest.fixture
def event_bus():
    """Fresh EventBus instance per test."""
    return EventBus()


# ── Fixtures: Heartbeat / Lock ────────────────────────────────────────────────

@pytest.fixture
def speaking_lock():
    """Fresh SpeakingLock per test."""
    return SpeakingLock()


@pytest.fixture
def heartbeat(event_bus):
    """Heartbeat wired to the test EventBus."""
    return Heartbeat(event_bus)


# ── Fixtures: Physics ─────────────────────────────────────────────────────────

@pytest.fixture
def physics(real_llm):
    """GamemasterPhysics with REAL Ollama LLM for architecture validation."""
    return GamemasterPhysics(real_llm)


@pytest.fixture
def mock_physics(mock_llm):
    """GamemasterPhysics with mock LLM for mechanical tests."""
    return GamemasterPhysics(mock_llm)


# ── Fixtures: Integrity Monitor ───────────────────────────────────────────────

@pytest.fixture
def integrity(real_llm):
    """IntegrityMonitor with REAL Ollama LLM."""
    return IntegrityMonitor(real_llm)


# ── Fixtures: Temp Agent Dir ──────────────────────────────────────────────────

@pytest.fixture
def tmp_agent_dir(ares_soul):
    """
    Temp directory with a soul_state.json for persistence tests.
    Returns the temp dir path. Cleaned up after test.
    """
    tmpdir = tempfile.mkdtemp()
    agent_dir = os.path.join(tmpdir, "agents", "general_ares")
    os.makedirs(agent_dir)
    
    state_path = os.path.join(agent_dir, "soul_state.json")
    with open(state_path, "w") as f:
        f.write(ares_soul.model_dump_json(indent=4))
    
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── Fixtures: All four agents ─────────────────────────────────────────────────

@pytest.fixture
def all_souls(ares_soul, dove_soul, midas_soul, logic_soul):
    """All four canonical council agent souls."""
    return {
        "general_ares": ares_soul,
        "diplomat_dove": dove_soul,
        "banker_midas": midas_soul,
        "analyst_logic": logic_soul,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_async(coro):
    """Run an async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
