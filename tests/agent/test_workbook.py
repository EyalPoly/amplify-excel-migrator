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
