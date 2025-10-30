# CI/CD Setup Guide

## Overview

This project uses GitHub Actions for continuous integration and continuous deployment (CI/CD).

## Workflows

### 1. **Tests** (`.github/workflows/test.yml`)

**Triggers**: Every push and pull request to main/master/develop branches

**What it does**:
- Runs tests on Python 3.8, 3.9, 3.10, 3.11, 3.12
- Tests on Ubuntu, macOS, and Windows
- Generates code coverage reports
- Uploads coverage to Codecov (optional)

**Status**: ✅ Active

---

### 2. **Lint** (`.github/workflows/lint.yml`)

**Triggers**: Every push and pull request to main/master/develop branches

**What it does**:
- Checks code style with flake8
- Checks formatting with black
- Checks import sorting with isort

**Status**: ✅ Active

---

### 3. **Publish to PyPI** (`.github/workflows/publish.yml`)

**Triggers**: Every push to `main` branch

**What it does**:
1. Automatically increments the patch version (1.0.0 → 1.0.1 → 1.0.2)
2. Updates `setup.py` with the new version
3. Commits the version bump back to main with `[skip ci]` tag
4. Creates a git tag (e.g., `v1.0.1`)
5. Builds the package (wheel + source distribution)
6. Publishes to PyPI
7. Creates a GitHub Release with built artifacts