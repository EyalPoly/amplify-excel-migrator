from __future__ import annotations

from pathlib import Path

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


def _parse_requirements() -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"core": [], "agent": [], "dev": []}
    section = "core"
    for raw in (Path(__file__).parent / "requirements.txt").read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            lowered = line.lower()
            if "agent" in lowered:
                section = "agent"
            elif "dev" in lowered:
                section = "dev"
            elif "core" in lowered:
                section = "core"
            continue
        buckets[section].append(line)
    return buckets


_requirements = _parse_requirements()

setup(
    name="amplify-excel-migrator",
    version="1.21.3",
    author="Eyal Politansky",
    author_email="10eyal10@gmail.com",
    description="A CLI tool to migrate Excel data to AWS Amplify",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EyalPoly/amplify-excel-migrator",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=_requirements["core"],
    extras_require={
        "agent": _requirements["agent"],
        "dev": _requirements["dev"],
    },
    entry_points={
        "console_scripts": [
            "amplify-migrator=amplify_excel_migrator.cli.commands:main",
        ],
    },
)
