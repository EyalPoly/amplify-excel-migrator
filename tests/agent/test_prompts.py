from amplify_excel_migrator.agent.prompts import SYSTEM_PROMPT


def test_prompt_states_the_approval_contract():
    text = SYSTEM_PROMPT.lower()
    assert "propose_changes" in text
    assert "never" in text and "approval" in text
    assert "dry_run" in text


def test_prompt_is_nonempty():
    assert len(SYSTEM_PROMPT.strip()) > 200
