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


def test_prompt_prefers_value_mappings_for_failure_groups():
    text = SYSTEM_PROMPT.lower()
    assert "propose_value_mappings" in text
    assert "group" in text


def test_prompt_requires_dry_run_before_value_fixes():
    text = SYSTEM_PROMPT.lower()
    assert "dry_run" in text
    assert "before any value fix" in text
    assert "after each applied batch" in text
