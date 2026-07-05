from amplify_excel_migrator.agent.prompts import SYSTEM_PROMPT


def test_prompt_states_the_approval_contract():
    text = SYSTEM_PROMPT.lower()
    assert "propose_changes" in text
    assert "never" in text and "approval" in text
    assert "dry_run" in text


def test_prompt_is_nonempty():
    assert len(SYSTEM_PROMPT.strip()) > 200


def test_prompt_states_the_rename_contract():
    text = SYSTEM_PROMPT.lower()
    assert "propose_column_renames" in text
    assert "rename" in text


def test_prompt_forbids_narrating_tool_calls_as_text():
    assert "NEVER write a tool call" in SYSTEM_PROMPT


def test_prompt_requires_calling_finish_to_complete():
    assert "finish" in SYSTEM_PROMPT
    assert "does NOT finish" in SYSTEM_PROMPT
