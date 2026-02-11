"""
Layer 2: Dream Phase — Test 5.1
=================================
Per ARCHITECTURE.md: "Post-session 'Dream Phase' where agents consolidate memories."
Per README: "Dreams are subjective diary entries reflecting the agent's biased perspective."
Per README: "Dream phase includes: bias injection, hidden agenda review, memory formation."

🔴 REAL OLLAMA — Tests validate dreams are character-biased, subjective,
and architecturally compliant with documented dream phase behavior.
"""

import pytest

from core.dream import dream_phase, dream_phase_stream, review_agendas
from core.llm import LLMService
from tests.helpers import SoulFactory, assert_keyword_present, assert_no_keyword_present


@pytest.fixture
def ares_agent_mock():
    """Minimal agent-like object for dream_phase (needs .soul, .agent_name, .memory)."""
    class MockAgent:
        def __init__(self, soul):
            self.soul = soul
            self.agent_name = "general_ares"
            self.memory = None
            self.llm = LLMService()  # Dream phase should handle None memory gracefully

        def save_state(self):
            pass

    return MockAgent(SoulFactory.ares(confidence=70, paranoia=40, stress=60))


@pytest.fixture
def dove_agent_mock():
    """Diplomat Dove agent-like object for dream_phase."""
    class MockAgent:
        def __init__(self, soul):
            self.soul = soul
            self.agent_name = "diplomat_dove"
            self.memory = None
            self.llm = LLMService()

        def save_state(self):
            pass

    return MockAgent(SoulFactory.dove(confidence=55, paranoia=20, stress=30))


@pytest.fixture
def session_transcript():
    """Realistic session transcript for dream phase input."""
    return [
        {"speaker": "Chairman", "content": "We need to discuss the border defense budget."},
        {"speaker": "General Ares", "content": "We must double our military spending. The threats are real."},
        {"speaker": "Diplomat Dove", "content": "I believe we should invest in diplomatic channels instead."},
        {"speaker": "Banker Midas", "content": "The numbers don't support a budget increase of that magnitude."},
        {"speaker": "General Ares", "content": "Midas, you're shortsighted. Without defense, there's nothing to profit from."},
        {"speaker": "Diplomat Dove", "content": "We should find a compromise that addresses both security and diplomacy."},
        {"speaker": "Chairman", "content": "The council will vote on this in the next session."},
    ]


class TestDreamPhaseOutput:
    """
    Per Architecture: dream_phase produces a subjective diary entry.
    The dream must be BIASED toward the agent's worldview, not objective.
    """

    @pytest.mark.anyio
    async def test_dream_returns_string(self, ares_agent_mock, session_transcript):
        """Per Architecture: dream_phase returns a diary entry string."""
        result = await dream_phase(ares_agent_mock, session_transcript)
        assert isinstance(result, str)
        assert len(result) > 50, "Dream diary entry is too short to be meaningful"

    @pytest.mark.anyio
    async def test_dream_is_subjective_not_objective(self, ares_agent_mock, session_transcript):
        """
        Per README: "Dreams are SUBJECTIVE diary entries reflecting the agent's biased perspective."
        General Ares should frame the budget debate through a military lens.
        """
        result = await dream_phase(ares_agent_mock, session_transcript)
        military_keywords = ["military", "defense", "budget", "threat", "strength",
                           "security", "power", "protect", "force", "war",
                           "fight", "strategic", "spend", "army"]
        assert_keyword_present(result, military_keywords, min_matches=2)

    @pytest.mark.anyio
    async def test_dove_dream_reflects_peace_perspective(self, dove_agent_mock, session_transcript):
        """
        Per README: Diplomat Dove should dream about peace/diplomacy, not warfare.
        """
        result = await dream_phase(dove_agent_mock, session_transcript)
        peace_keywords = ["peace", "diplomacy", "negotiat", "cooperat", "dialogue",
                         "compromise", "understand", "agree", "calm", "resolv",
                         "mediati", "ally", "partner"]
        assert_keyword_present(result, peace_keywords, min_matches=1)

    @pytest.mark.anyio
    async def test_dream_references_session_events(self, ares_agent_mock, session_transcript):
        """
        Per Architecture: Dream should reference actual events from the session transcript.
        """
        result = await dream_phase(ares_agent_mock, session_transcript)
        # Dream should mention at least one thing that happened in the session
        session_keywords = ["budget", "midas", "dove", "chairman", "vote", "spending",
                           "defense", "diplomat"]
        assert_keyword_present(result, session_keywords, min_matches=1)


class TestDreamPhaseStream:
    """
    Per Architecture: dream_phase_stream is an async generator for real-time streaming.
    """

    @pytest.mark.anyio
    async def test_dream_stream_yields_chunks(self, ares_agent_mock, session_transcript):
        """Per Architecture: Streaming dream yields text chunks for WebSocket broadcast."""
        chunks = []
        async for chunk in dream_phase_stream(ares_agent_mock, session_transcript):
            chunks.append(chunk)
            if len(chunks) > 5:  # Don't consume entire stream, just verify it works
                break

        assert len(chunks) > 0, "Dream stream produced zero chunks — streaming is broken"
        full_text = "".join(chunks)
        assert len(full_text) > 10, "Dream stream chunks too short — possible empty generation"

    @pytest.mark.anyio
    async def test_dream_stream_accepts_trust_deltas(self, ares_agent_mock, session_transcript):
        """
        Per Architecture: dream_phase_stream accepts trust_deltas parameter
        to inject context about trust score changes during the session.
        """
        trust_deltas = {"Diplomat Dove": -15, "Banker Midas": 5}
        chunks = []
        async for chunk in dream_phase_stream(ares_agent_mock, session_transcript, trust_deltas=trust_deltas):
            chunks.append(chunk)
            if len(chunks) > 5:
                break

        assert len(chunks) > 0, "Dream stream with trust deltas produced no output"


class TestDreamAgendaReview:
    """
    Per Architecture: review_agendas updates hidden agendas based on session outcomes.
    """

    @pytest.mark.anyio
    async def test_review_agendas_callable(self, ares_agent_mock):
        """Per Architecture: review_agendas must be an async function."""
        import asyncio
        assert asyncio.iscoroutinefunction(review_agendas), \
            "review_agendas must be async — required for event-driven architecture"
