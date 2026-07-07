from amplify_excel_migrator.agent.tools import TOOL_SPECS, GATED_TOOLS, tool_names


def test_expected_tools_present():
    assert tool_names() == [
        "inspect_schema",
        "read_sheet",
        "dry_run",
        "propose_changes",
        "upload",
        "propose_column_renames",
        "propose_value_mappings",
        "finish",
    ]


def test_gated_tools_are_propose_upload_rename_and_value_mappings():
    assert GATED_TOOLS == {"propose_changes", "upload", "propose_column_renames", "propose_value_mappings"}


def test_every_spec_has_object_schema():
    for spec in TOOL_SPECS:
        assert spec.input_schema["type"] == "object"


def test_propose_changes_schema_requires_changes_array():
    spec = next(s for s in TOOL_SPECS if s.name == "propose_changes")
    props = spec.input_schema["properties"]
    assert props["changes"]["type"] == "array"
    item = props["changes"]["items"]["properties"]
    assert {"sheet_name", "row", "column", "proposed_value", "rationale"} <= set(item)


def test_propose_column_renames_schema_shape():
    spec = next(s for s in TOOL_SPECS if s.name == "propose_column_renames")
    props = spec.input_schema["properties"]
    assert props["renames"]["type"] == "array"
    item = props["renames"]["items"]["properties"]
    assert {"sheet_name", "current_name", "new_name", "rationale"} <= set(item)
    assert set(spec.input_schema["required"]) == {"summary", "renames"}


def test_finish_tool_present_and_not_gated():
    assert "finish" in tool_names()
    assert "finish" not in GATED_TOOLS


def test_finish_schema_has_optional_summary():
    spec = next(s for s in TOOL_SPECS if s.name == "finish")
    props = spec.input_schema["properties"]
    assert props["summary"]["type"] == "string"
    assert spec.input_schema.get("required", []) == []


def test_propose_value_mappings_schema_shape():
    spec = next(s for s in TOOL_SPECS if s.name == "propose_value_mappings")
    props = spec.input_schema["properties"]
    assert props["mappings"]["type"] == "array"
    item = props["mappings"]["items"]["properties"]
    assert {"sheet_name", "column", "from_value", "to_value", "rationale"} <= set(item)
    assert set(spec.input_schema["required"]) == {"summary", "mappings"}
    required_item = set(spec.input_schema["properties"]["mappings"]["items"]["required"])
    assert required_item == {"sheet_name", "column", "from_value", "to_value", "rationale"}
