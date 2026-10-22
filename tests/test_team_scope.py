"""Tests for team-scoped writes: group names, scope detection, and team resolution"""

import pytest
from unittest.mock import MagicMock

from amplify_excel_migrator.core.permissions import SUPER_ADMINS, admin_group, editor_groups_for, user_group
from amplify_excel_migrator.graphql.team_scope import TeamResolver, TeamScope, detect_team_scope

SUBMIT_ARGS = {"teamSlug": "String", "sequentialId": "Int!", "date": "AWSDate!", "speciesId": "ID!"}


def schema_with(mutations):
    schema = MagicMock()
    schema.get_mutation_args.side_effect = lambda name: mutations.get(name)
    return schema


class TestGroupNames:
    def test_super_admins(self):
        assert SUPER_ADMINS == "SUPER_ADMINS"

    def test_team_groups(self):
        assert user_group("ISRAEL") == "ISRAEL_USER"
        assert admin_group("ISRAEL") == "ISRAEL_ADMIN"
        assert editor_groups_for("GREECE") == ["GREECE_USER", "GREECE_ADMIN"]


class TestDetectTeamScope:
    def test_submit_mutation_with_team_slug_and_review(self):
        schema = schema_with(
            {"submitObservation": SUBMIT_ARGS, "reviewObservation": {"id": "ID!", "decision": "String"}}
        )

        scope = detect_team_scope(schema, "Observation", ["sequentialId", "groupId", "editorGroups"])

        assert scope.submit_mutation == "submitObservation"
        assert scope.submit_args == SUBMIT_ARGS
        assert scope.review_mutation == "reviewObservation"
        assert scope.review_args == {"id": "ID!"}
        assert scope.stamp_editor_groups is False

    def test_submit_mutation_without_review(self):
        scope = detect_team_scope(schema_with({"submitObservation": SUBMIT_ARGS}), "Observation", [])

        assert scope.submit_mutation == "submitObservation"
        assert scope.review_mutation is None
        assert scope.review_args == {}

    def test_review_mutation_without_id_arg_is_ignored(self):
        schema = schema_with({"submitObservation": SUBMIT_ARGS, "reviewObservation": {"key": "String"}})

        scope = detect_team_scope(schema, "Observation", [])

        assert scope.review_mutation is None

    def test_submit_mutation_without_team_slug_is_not_team_scoped(self):
        schema = schema_with({"submitObservation": {"sequentialId": "Int!"}})

        assert detect_team_scope(schema, "Observation", ["sequentialId"]) is None

    def test_editor_groups_and_group_id_fields_stamp(self):
        scope = detect_team_scope(schema_with({}), "SpeciesCommonName", ["name", "groupId", "editorGroups"])

        assert scope == TeamScope(stamp_editor_groups=True)

    def test_editor_groups_without_group_id_is_not_team_scoped(self):
        # Media: editorGroups is re-derived server-side from its parent observation
        assert detect_team_scope(schema_with({}), "Media", ["url", "observationId", "editorGroups"]) is None

    def test_plain_model_is_not_team_scoped(self):
        assert detect_team_scope(schema_with({}), "Species", ["name", "scientificName"]) is None


class TestTeamScopeSubmitHelpers:
    def test_submit_variables_keep_only_accepted_args_and_add_team_slug(self):
        scope = TeamScope(submit_mutation="submitObservation", submit_args=SUBMIT_ARGS)
        record = {"sequentialId": 7, "date": "2024-01-01", "groupId": "g-1", "checkDate": "2024-02-01T00:00:00Z"}

        assert scope.submit_variables(record, "ISRAEL") == {
            "sequentialId": 7,
            "date": "2024-01-01",
            "teamSlug": "ISRAEL",
        }

    def test_dropped_fields_excludes_accepted_args_and_group_id(self):
        scope = TeamScope(submit_mutation="submitObservation", submit_args=SUBMIT_ARGS)
        records = [
            {"sequentialId": 1, "groupId": "g", "checkDate": "x"},
            {"sequentialId": 2, "groupId": "g", "reviewStatus": "APPROVED"},
        ]

        assert scope.dropped_fields(records) == ["checkDate", "reviewStatus"]

    def test_dropped_fields_empty_in_stamp_mode(self):
        assert TeamScope(stamp_editor_groups=True).dropped_fields([{"anything": 1}]) == []


class TestTeamResolver:
    @pytest.fixture
    def lister(self):
        return MagicMock()

    def test_resolves_slug_field(self, lister):
        lister.list_records_by_field.return_value = [{"id": "g-1", "name": "Israel", "slug": "ISRAEL"}]

        resolver = TeamResolver(lister)

        assert resolver.slug_for("g-1") == "ISRAEL"
        lister.list_records_by_field.assert_called_once_with("Group", "name", fields=["id", "name", "slug"])

    def test_loads_groups_once(self, lister):
        lister.list_records_by_field.return_value = [{"id": "g-1", "name": "Israel", "slug": "ISRAEL"}]
        resolver = TeamResolver(lister)

        resolver.slug_for("g-1")
        resolver.slug_for("g-2")

        assert lister.list_records_by_field.call_count == 1

    def test_falls_back_to_name_when_slug_query_fails(self, lister):
        lister.list_records_by_field.side_effect = [None, [{"id": "g-1", "name": " Greece "}]]

        resolver = TeamResolver(lister)

        assert resolver.slug_for("g-1") == "GREECE"
        assert lister.list_records_by_field.call_args_list[1].kwargs["fields"] == ["id", "name"]

    def test_falls_back_to_name_when_row_slug_is_null(self, lister):
        lister.list_records_by_field.return_value = [{"id": "g-1", "name": "Israel", "slug": None}]

        assert TeamResolver(lister).slug_for("g-1") == "ISRAEL"

    def test_unknown_or_missing_group_id(self, lister):
        lister.list_records_by_field.return_value = [{"id": "g-1", "name": "Israel", "slug": "ISRAEL"}]
        resolver = TeamResolver(lister)

        assert resolver.slug_for("g-404") is None
        assert resolver.slug_for(None) is None

    def test_require_slug_raises_for_unresolvable_group(self, lister):
        lister.list_records_by_field.return_value = []

        with pytest.raises(ValueError, match="g-404"):
            TeamResolver(lister).require_slug({"groupId": "g-404"})

    def test_require_slug_raises_without_group_id(self, lister):
        with pytest.raises(ValueError, match="groupId"):
            TeamResolver(lister).require_slug({"name": "x"})

    def test_with_editor_groups_stamps_team_groups(self, lister):
        lister.list_records_by_field.return_value = [{"id": "g-1", "name": "Israel", "slug": "ISRAEL"}]

        record = TeamResolver(lister).with_editor_groups({"name": "Blue shark", "groupId": "g-1"})

        assert record == {"name": "Blue shark", "groupId": "g-1", "editorGroups": ["ISRAEL_USER", "ISRAEL_ADMIN"]}

    def test_with_editor_groups_keeps_provided_value(self, lister):
        record = {"name": "Blue shark", "groupId": "g-1", "editorGroups": ["GREECE_USER"]}

        assert TeamResolver(lister).with_editor_groups(record) is record
        lister.list_records_by_field.assert_not_called()
