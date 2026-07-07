import pandas as pd
from amplify_excel_migrator.agent.workbook import WorkbookEditor


def _editor():
    return WorkbookEditor({"Reporter": pd.DataFrame({"name": ["a", "b"], "country": ["IL", ""]})})


def test_sheet_names():
    assert _editor().sheet_names() == ["Reporter"]


def test_preview_returns_columns_and_sample_rows():
    preview = _editor().preview("Reporter", max_rows=1)
    assert preview["columns"] == ["name", "country"]
    assert preview["row_count"] == 2
    assert preview["rows"] == [{"name": "a", "country": "IL"}]


def test_apply_change_updates_cell():
    editor = _editor()
    editor.apply_change("Reporter", row=1, column="country", value="EG")
    assert editor.cell("Reporter", 1, "country") == "EG"


def test_apply_change_rejects_unknown_column():
    editor = _editor()
    try:
        editor.apply_change("Reporter", row=0, column="nope", value="x")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_save_roundtrips(tmp_path):
    editor = _editor()
    editor.apply_change("Reporter", row=1, column="country", value="EG")
    out = tmp_path / "edited.xlsx"
    editor.save(str(out))
    reloaded = pd.read_excel(out, sheet_name="Reporter")
    assert reloaded.loc[1, "country"] == "EG"


def test_rename_column_renames_header():
    editor = _editor()
    editor.rename_column("Reporter", "country", "siteId")
    assert list(editor.sheets()["Reporter"].columns) == ["name", "siteId"]


def test_rename_column_missing_source_raises_keyerror():
    editor = _editor()
    try:
        editor.rename_column("Reporter", "nope", "siteId")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_rename_column_existing_target_raises_valueerror():
    editor = _editor()
    try:
        editor.rename_column("Reporter", "country", "name")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_accepts_a_binary_buffer():
    import io

    buf = io.BytesIO()
    _editor().save(buf)
    buf.seek(0)
    reloaded = pd.read_excel(buf, sheet_name="Reporter")
    assert list(reloaded.columns) == ["name", "country"]


def test_apply_value_mapping_rewrites_all_matching_rows():
    editor = WorkbookEditor({"S": pd.DataFrame({"species": ["#REF!", "cat", "#REF!"]})})
    changed = editor.apply_value_mapping("S", "species", "#REF!", "UNKNOWN")
    assert changed == 2
    assert list(editor.sheets()["S"]["species"]) == ["UNKNOWN", "cat", "UNKNOWN"]


def test_apply_value_mapping_matches_blank_cells_when_from_value_is_none():
    editor = WorkbookEditor({"S": pd.DataFrame({"species": ["cat", None, float("nan")]})})
    changed = editor.apply_value_mapping("S", "species", None, "UNKNOWN")
    assert changed == 2
    assert list(editor.sheets()["S"]["species"]) == ["cat", "UNKNOWN", "UNKNOWN"]


def test_apply_value_mapping_unknown_column_raises_keyerror():
    editor = WorkbookEditor({"S": pd.DataFrame({"species": ["cat"]})})
    try:
        editor.apply_value_mapping("S", "nope", "cat", "dog")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_apply_value_mapping_absent_value_raises_valueerror():
    editor = WorkbookEditor({"S": pd.DataFrame({"species": ["cat"]})})
    try:
        editor.apply_value_mapping("S", "species", "#REF!", "UNKNOWN")
        assert False, "expected ValueError"
    except ValueError:
        pass
