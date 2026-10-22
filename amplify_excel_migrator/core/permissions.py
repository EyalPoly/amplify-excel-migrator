"""Cognito group names of the team-based permission model.

A team and a role share one group name (`<SLUG>_USER` / `<SLUG>_ADMIN`) because
"admin" only means anything relative to a team; `SUPER_ADMINS` spans all teams.
"""

from typing import List

SUPER_ADMINS = "SUPER_ADMINS"


def user_group(team_slug: str) -> str:
    return f"{team_slug}_USER"


def admin_group(team_slug: str) -> str:
    return f"{team_slug}_ADMIN"


def editor_groups_for(team_slug: str) -> List[str]:
    return [user_group(team_slug), admin_group(team_slug)]
