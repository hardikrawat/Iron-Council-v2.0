"""
Layer 1: Schema Mechanics — Test 3.3 (Deterministic Stat Updates)
=================================================================
Per ARCHITECTURE.md: "All stat changes are deterministic and bounded."
Per README.md: Stats clamped 0-100, trust clamped -100 to +100.

These tests validate the SCHEMA LAYER enforces documented constraints.
"""

import pytest
from pydantic import ValidationError
from core.schema import AgentSoul, DynamicStats, RelationshipModel, Goal


# ── Stat Clamping (Architecture: "Mutable stats constrained between 0 and 100") ──

class TestStatClamping:
    """Per docs: DynamicStats fields are constrained between 0 and 100."""

    def test_stat_clamping_upper_bound(self, make_soul):
        """Updating a stat beyond 100 must clamp to 100."""
        soul = make_soul(stats={"confidence": 90})
        soul.update_stat("confidence", 20)  # 90 + 20 = 110 → clamped to 100
        assert soul.dynamic_stats.confidence == 100

    def test_stat_clamping_lower_bound(self, make_soul):
        """Updating a stat below 0 must clamp to 0."""
        soul = make_soul(stats={"paranoia": 5})
        soul.update_stat("paranoia", -20)  # 5 - 20 = -15 → clamped to 0
        assert soul.dynamic_stats.paranoia == 0

    def test_stat_clamping_at_boundary(self, make_soul):
        """Stat at 100 + 0 stays at 100."""
        soul = make_soul(stats={"energy": 100})
        soul.update_stat("energy", 0)
        assert soul.dynamic_stats.energy == 100

    def test_stat_clamping_at_zero(self, make_soul):
        """Stat at 0 - 50 stays at 0."""
        soul = make_soul(stats={"stress_level": 0})
        soul.update_stat("stress_level", -50)
        assert soul.dynamic_stats.stress_level == 0

    def test_all_five_stats_exist(self, make_soul):
        """Architecture mandates 5 dynamic stats: confidence, paranoia, loyalty, stress, energy."""
        soul = make_soul()
        stats = soul.dynamic_stats
        assert hasattr(stats, "confidence")
        assert hasattr(stats, "paranoia")
        assert hasattr(stats, "loyalty_to_chairman")
        assert hasattr(stats, "stress_level")
        assert hasattr(stats, "energy")

    def test_invalid_stat_name_raises(self, make_soul):
        """Updating a non-existent stat must raise AttributeError."""
        soul = make_soul()
        with pytest.raises(AttributeError):
            soul.update_stat("charisma", 10)


# ── Relationship Clamping (Architecture: trust_score between -100 and 100) ──

class TestRelationshipClamping:
    """Per docs: Trust scores clamped between -100 and +100."""

    def test_trust_clamping_upper_bound(self, make_soul):
        """Trust above 100 clamps to 100."""
        soul = make_soul()
        soul.update_relationship("Banker Midas", 200)  # 32 + 200 → clamped to 100
        assert soul.relationships["Banker Midas"].trust_score == 100

    def test_trust_clamping_lower_bound(self, make_soul):
        """Trust below -100 clamps to -100."""
        soul = make_soul()
        soul.update_relationship("Diplomat Dove", -200)  # -50 - 200 → clamped to -100
        assert soul.relationships["Diplomat Dove"].trust_score == -100

    def test_missing_relationship_auto_creates(self, make_soul):
        """Per docs: update_relationship creates entry if it doesn't exist."""
        soul = make_soul()
        soul.update_relationship("New Agent", 25)
        assert "New Agent" in soul.relationships
        assert soul.relationships["New Agent"].trust_score == 25

    def test_relationship_summary_updates(self, make_soul):
        """Interaction summary updates when provided."""
        soul = make_soul()
        soul.update_relationship("Banker Midas", 5, summary="Agreed on budget cuts")
        assert "budget" in soul.relationships["Banker Midas"].last_interaction_summary.lower()


# ── Goal Progress (Architecture: "Goals with progress >= 100 are auto-deactivated") ──

class TestGoalProgress:
    """Per docs: Goal progress clamped 0-100, auto-deactivation at 100."""

    def test_goal_progress_clamping_upper(self, make_soul):
        """Progress cannot exceed 100."""
        soul = make_soul()
        soul.update_goal_progress("Secure military budget increase", 150)
        assert soul.goals[0].progress == 100

    def test_goal_progress_clamping_lower(self, make_soul):
        """Progress cannot go below 0."""
        soul = make_soul()
        soul.update_goal_progress("Secure military budget increase", -50)
        assert soul.goals[0].progress == 0

    def test_goal_auto_deactivation(self, make_soul):
        """Per docs: Goals at 100% progress become inactive."""
        soul = make_soul()
        soul.update_goal_progress("Secure military budget increase", 100)
        completed = soul.check_goal_completion()
        assert "Secure military budget increase" in completed
        assert soul.goals[0].active is False

    def test_goal_fuzzy_matching(self, make_soul):
        """Per docs: Partial word matching works for goal updates."""
        soul = make_soul()
        soul.update_goal_progress("military budget", 30)
        assert soul.goals[0].progress == 30

    def test_inactive_goal_not_updated(self, make_soul):
        """Inactive goals should not be modified by updates."""
        soul = make_soul()
        soul.goals[0].active = False
        soul.goals[0].progress = 80
        soul.update_goal_progress("Secure military budget increase", 20)
        assert soul.goals[0].progress == 80  # Unchanged


# ── Pydantic Validation (Architecture: Schema enforcement) ──

class TestPydanticValidation:
    """Per README: Pydantic enforces data validation and schema constraints."""

    def test_pydantic_rejects_stat_over_100(self):
        """DynamicStats should reject values over 100 at construction."""
        with pytest.raises(ValidationError):
            DynamicStats(confidence=150)

    def test_pydantic_rejects_negative_energy(self):
        """DynamicStats should reject negative energy at construction."""
        with pytest.raises(ValidationError):
            DynamicStats(energy=-10)

    def test_pydantic_rejects_trust_over_100(self):
        """RelationshipModel should reject trust > 100."""
        with pytest.raises(ValidationError):
            RelationshipModel(trust_score=150)

    def test_pydantic_rejects_trust_under_neg100(self):
        """RelationshipModel should reject trust < -100."""
        with pytest.raises(ValidationError):
            RelationshipModel(trust_score=-150)

    def test_pydantic_rejects_goal_progress_over_100(self):
        """Goal should reject progress > 100."""
        with pytest.raises(ValidationError):
            Goal(description="Test", progress=150)

    def test_pydantic_rejects_negative_goal_progress(self):
        """Goal should reject negative progress."""
        with pytest.raises(ValidationError):
            Goal(description="Test", progress=-10)


# ── Serialization (Architecture: "Agent Soul persisted as JSON") ──

class TestSerialization:
    """Per docs: Soul state must roundtrip cleanly to/from JSON."""

    def test_get_serializable_relationships(self, make_soul):
        """get_serializable_relationships returns plain dicts, not Pydantic models."""
        soul = make_soul()
        serialized = soul.get_serializable_relationships()
        assert isinstance(serialized, dict)
        for name, data in serialized.items():
            assert isinstance(data, dict)
            assert "trust_score" in data
            assert "last_interaction_summary" in data
            assert "hidden_agenda" in data

    def test_soul_json_roundtrip(self, make_soul):
        """Soul can be serialized to JSON and reconstructed identically."""
        soul = make_soul()
        json_str = soul.model_dump_json()
        restored = AgentSoul.model_validate_json(json_str)
        assert restored.name == soul.name
        assert restored.dynamic_stats.confidence == soul.dynamic_stats.confidence
        assert len(restored.relationships) == len(soul.relationships)

    def test_get_relationship_score_existing(self, make_soul):
        """get_relationship_score returns correct score for existing relationship."""
        soul = make_soul()
        assert soul.get_relationship_score("Diplomat Dove") == -50

    def test_get_relationship_score_missing(self, make_soul):
        """get_relationship_score returns 0 for non-existent relationship."""
        soul = make_soul()
        assert soul.get_relationship_score("Unknown Agent") == 0
