"""Binding created records to a team under group-based (team) permissions.

A team-scoped model is readable only by Cognito groups listed on the row, so a
record created without them is invisible to its own team. Two shapes exist:

- the model's writes go through a `submit<Model>` custom mutation that takes a
  `teamSlug` and stamps the team server-side (generated `create<Model>` is denied);
- the model has an `editorGroups` field plus a `groupId`, and the creator stamps
  `editorGroups` itself.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol

from amplify_excel_migrator.core.permissions import editor_groups_for

logger = logging.getLogger(__name__)

TEAM_SLUG_ARG = "teamSlug"
TEAM_FIELD = "groupId"
EDITOR_GROUPS_FIELD = "editorGroups"


class _MutationSchema(Protocol):
    def get_mutation_args(self, mutation_name: str) -> Optional[Dict[str, str]]: ...


class _RecordLister(Protocol):
    def list_records_by_field(
        self, model_name: str, field_name: str, value: Optional[str] = None, fields: Optional[List[str]] = None
    ) -> Optional[List[Dict]]: ...


@dataclass
class TeamScope:
    submit_mutation: Optional[str] = None
    submit_args: Dict[str, str] = field(default_factory=dict)
    review_mutation: Optional[str] = None
    review_args: Dict[str, str] = field(default_factory=dict)
    stamp_editor_groups: bool = False

    def submit_variables(self, record: Dict[str, Any], team_slug: str) -> Dict[str, Any]:
        variables = {key: value for key, value in record.items() if key in self.submit_args}
        variables[TEAM_SLUG_ARG] = team_slug
        return variables

    def dropped_fields(self, records: Iterable[Dict[str, Any]]) -> List[str]:
        """Record fields the submit mutation doesn't accept (the team field is consumed as teamSlug)."""
        if not self.submit_mutation:
            return []
        present = {key for record in records for key in record}
        return sorted(present - set(self.submit_args) - {TEAM_FIELD})


def detect_team_scope(schema: _MutationSchema, model_name: str, field_names: Iterable[str]) -> Optional[TeamScope]:
    submit_mutation = f"submit{model_name}"
    submit_args = schema.get_mutation_args(submit_mutation)
    if submit_args and TEAM_SLUG_ARG in submit_args:
        review_mutation = f"review{model_name}"
        review_args = schema.get_mutation_args(review_mutation) or {}
        has_review = "id" in review_args
        return TeamScope(
            submit_mutation=submit_mutation,
            submit_args=submit_args,
            review_mutation=review_mutation if has_review else None,
            review_args={"id": review_args["id"]} if has_review else {},
        )

    if {EDITOR_GROUPS_FIELD, TEAM_FIELD} <= set(field_names):
        return TeamScope(stamp_editor_groups=True)

    return None


class TeamResolver:
    """Maps a Group id to its team slug, the prefix of that team's Cognito groups."""

    def __init__(self, lister: _RecordLister):
        self._lister = lister
        self._slugs: Optional[Dict[str, str]] = None

    def slug_for(self, group_id: Optional[str]) -> Optional[str]:
        if not group_id:
            return None
        if self._slugs is None:
            self._slugs = self._load()
        return self._slugs.get(group_id)

    def require_slug(self, record: Dict[str, Any]) -> str:
        group_id = record.get(TEAM_FIELD)
        slug = self.slug_for(group_id)
        if not slug:
            raise ValueError(f"Cannot resolve the team of {TEAM_FIELD} '{group_id}' (no Group with a slug or name)")
        return slug

    def with_editor_groups(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if record.get(EDITOR_GROUPS_FIELD):
            return record
        return {**record, EDITOR_GROUPS_FIELD: editor_groups_for(self.require_slug(record))}

    def _load(self) -> Dict[str, str]:
        rows = self._lister.list_records_by_field("Group", "name", fields=["id", "name", "slug"])
        if rows is None:
            # Selecting `slug` fails outright if any Group row predates it, so fall back to
            # deriving the slug from the name, as the backend's own backfill does.
            logger.warning("Could not read Group.slug; deriving team slugs from Group names")
            rows = self._lister.list_records_by_field("Group", "name", fields=["id", "name"])

        slugs: Dict[str, str] = {}
        for row in rows or []:
            slug = row.get("slug") or row.get("name")
            if slug:
                slugs[row["id"]] = str(slug).strip().upper()
        return slugs
