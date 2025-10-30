#!/usr/bin/env python3
"""Script to automatically bump patch version in setup.py"""
import re
import sys


def get_current_version(setup_file="setup.py"):
    with open(setup_file, "r") as f:
        content = f.read()

    match = re.search(r'version\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+)["\']', content)
    if not match:
        raise ValueError("Could not find version in setup.py")

    return match.group(1)


def bump_patch_version(version):
    major, minor, patch = version.split(".")
    new_patch = int(patch) + 1
    return f"{major}.{minor}.{new_patch}"


def update_version_in_file(setup_file, old_version, new_version):
    with open(setup_file, "r") as f:
        content = f.read()

    pattern = rf'version\s*=\s*["\']({re.escape(old_version)})["\']'
    new_content = re.sub(pattern, f'version="{new_version}"', content)

    with open(setup_file, "w") as f:
        f.write(new_content)

    return new_version


def main():
    setup_file = "setup.py"

    try:
        current_version = get_current_version(setup_file)
        print(f"Current version: {current_version}")

        new_version = bump_patch_version(current_version)
        print(f"New version: {new_version}")

        update_version_in_file(setup_file, current_version, new_version)
        print(f"Updated {setup_file}")

        # Output for GitHub Actions
        print(f"::set-output name=version::{new_version}")
        print(f"::set-output name=old_version::{current_version}")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
