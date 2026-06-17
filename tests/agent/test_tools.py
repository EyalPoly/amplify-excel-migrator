from amplify_excel_migrator.agent.tools import TOOL_SPECS, GATED_TOOLS, tool_names


def test_expected_tools_present():
    assert tool_names() == ["inspect_schema", "read_sheet", "dry_run", "propose_changes", "upload"]


def test_gated_tools_are_propose_and_upload():
    assert GATED_TOOLS == {"propose_changes", "upload"}


def test_every_spec_has_object_schema():
    for spec in TOOL_SPECS:
        assert spec.input_schema["type"] == "object"


def test_propose_changes_schema_requires_changes_array():
    spec = next(s for s in TOOL_SPECS if s.name == "propose_changes")
    props = spec.input_schema["properties"]
    assert props["changes"]["type"] == "array"
    item = props["changes"]["items"]["properties"]
    assert {"sheet_name", "row", "column", "proposed_value", "rationale"} <= set(item)
