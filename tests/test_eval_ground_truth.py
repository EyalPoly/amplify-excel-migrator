"""The trajectory eval's rename grader must score against the fixture alone.

These pin the properties the grader exists to have: it can reject as readily as it
approves, it never guesses from string similarity, and a fixture gap is visible rather
than silently scored as agent error."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_agent_trajectory import GroundTruth, load_ground_truth  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "header_ground_truth.yaml"


@pytest.fixture
def gt():
    return GroundTruth({"Observation": {"Media": "mediaPlatfrom", "Lat Lon": None, "Reporter": "reporterId"}})


def test_correct_rename_approved(gt):
    assert gt.judge("Observation", "Media", "mediaPlatfrom")[0] == "approved"


def test_wrong_rename_rejected_even_when_textually_similar(gt):
    """'mediaSourceId' shares the 'media' prefix; a similarity heuristic would approve it."""
    decision, reason = gt.judge("Observation", "Media", "mediaSourceId")
    assert decision == "rejected"
    assert "mediaPlatfrom" in reason


def test_header_with_no_correct_field_rejects_every_rename(gt):
    assert gt.judge("Observation", "Lat Lon", "latitude")[0] == "rejected"
    assert gt.judge("Observation", "Lat Lon", "longitude")[0] == "rejected"


def test_uncovered_header_is_unknown_not_approved(gt):
    decision, reason = gt.judge("Observation", "Disk length", "depth")
    assert decision == "unknown"
    assert "no ground truth" in reason


def test_uncovered_sheet_is_unknown(gt):
    assert gt.judge("Reporter", "Media", "mediaPlatfrom")[0] == "unknown"


def test_header_lookup_ignores_case_and_surrounding_space(gt):
    assert gt.judge("Observation", "  reporter ", "reporterId")[0] == "approved"


def test_field_comparison_is_exact(gt):
    """Field names are compared exactly — camelCase must match, unlike header lookup."""
    assert gt.judge("Observation", "Reporter", "reporterid")[0] == "rejected"


def test_missing_fixture_exits_rather_than_scoring_blind(tmp_path):
    with pytest.raises(SystemExit):
        load_ground_truth(str(tmp_path / "absent.yaml"))


def test_real_fixture_grades_the_media_swap_both_ways():
    """The bug the fixture replaced: a substring gate approved 'Media' against both media fields."""
    real = load_ground_truth(str(FIXTURE))
    assert real.judge("Observation", "Media", "mediaPlatfrom")[0] == "approved"
    assert real.judge("Observation", "Media", "mediaSourceId")[0] == "rejected"
    assert real.judge("Observation", "Documentation", "mediaSourceId")[0] == "approved"
    assert real.judge("Observation", "Documentation", "mediaPlatfrom")[0] == "rejected"


def test_real_fixture_rejects_the_length_distance_trap():
    real = load_ground_truth(str(FIXTURE))
    assert real.judge("Observation", "Length (cm)", "distance")[0] == "rejected"
    assert real.judge("Observation", "Distance [m]", "distance")[0] == "approved"
