import pytest
from utils.formatting import clean_agent_response


class TestResponseFormatting:
    def test_strip_name_prefix(self):
        assert (
            clean_agent_response("General Ares: We attack at dawn.", "general_ares")
            == "We attack at dawn."
        )
        assert clean_agent_response("Ares: We attack.", "general_ares") == "We attack."
        assert (
            clean_agent_response("**General Ares**: The time is now.", "general_ares")
            == "The time is now."
        )

    def test_strip_meta_dialogue_prefix(self):
        # Current implementation fails this
        assert (
            clean_agent_response("As General Ares: I concur.", "general_ares")
            == "I concur."
        )
        assert (
            clean_agent_response("Speaking as General Ares: No.", "general_ares")
            == "No."
        )

    def test_strip_recipient_markers(self):
        # Current implementation only handles bold
        assert (
            clean_agent_response("To the council: We must act.", "general_ares")
            == "We must act."
        )
        assert (
            clean_agent_response("**To Diplomat Dove:** I agree.", "general_ares")
            == "I agree."
        )
        assert (
            clean_agent_response("To everyone: Silence!", "general_ares") == "Silence!"
        )

    def test_strip_quotes_and_markdown(self):
        assert (
            clean_agent_response('"We are strong."', "general_ares") == "We are strong."
        )
        assert (
            clean_agent_response("'We are strong.'", "general_ares") == "We are strong."
        )
        assert (
            clean_agent_response("**We are strong.**", "general_ares")
            == "We are strong."
        )
        assert (
            clean_agent_response("```We are strong.```", "general_ares")
            == "We are strong."
        )

    def test_case_insensitivity(self):
        assert clean_agent_response("general ares: yes", "general_ares") == "yes"
