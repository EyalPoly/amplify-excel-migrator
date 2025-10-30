# Branch Protection Setup Guide

## Overview

Branch protection rules prevent pull requests from being merged to `main` until all required checks pass.

## Setting Up Branch Protection

### Step 1: Navigate to Branch Protection Settings

1. Go to your repository: https://github.com/EyalPoly/amplify-excel-migrator
2. Click **Settings** (top right)
3. Click **Branches** (left sidebar)
4. Under "Branch protection rules", click **Add rule** (or **Add branch protection rule**)

### Step 2: Configure the Rule

#### Branch Name Pattern
```
main
```

#### Protection Settings

Check the following boxes:

##### ✅ Require a pull request before merging
- **Required approvals**: 0 (or 1 if you want code review)
- ✅ **Dismiss stale pull request approvals when new commits are pushed** (recommended)
- ☐ Require review from Code Owners (optional)

##### ✅ Require status checks to pass before merging
This is the **most important** setting to prevent merging failing PRs.

- ✅ **Require branches to be up to date before merging** (recommended)

Click **"Add status checks"** and search for:
- `test` (or the specific test jobs like `test (ubuntu-latest, 3.11)`)
- `lint`

**Note**: Status checks won't appear until they've run at least once. You may need to:
1. Push your CI/CD branch first
2. Create a test PR to trigger the workflows
3. Come back and add the status checks after they appear

##### ✅ Require conversation resolution before merging (optional)
- Ensures all PR comments are resolved before merge

##### ✅ Require signed commits (optional, advanced)
- For extra security

##### ✅ Require linear history (recommended)
- Prevents merge commits, keeps history clean
- Requires squash or rebase merging

##### ✅ Do not allow bypassing the above settings
- Enforces rules for everyone, including admins

**Exception**: You may want to allow `github-actions[bot]` to bypass rules so it can push version bumps. To do this:
- Under "Allow specific actors to bypass required pull requests"
- Add: `github-actions[bot]`

##### ☐ Allow force pushes
- **Keep this UNCHECKED** (force pushes can break history)

##### ☐ Allow deletions
- **Keep this UNCHECKED** (prevents accidental branch deletion)

### Step 3: Save Changes

Click **Create** (or **Save changes**)

---

## Required Status Checks

After your CI/CD workflows run at least once, you'll see these checks available:

### From `test.yml`:
- `test (ubuntu-latest, 3.8)`
- `test (ubuntu-latest, 3.9)`
- `test (ubuntu-latest, 3.10)`
- `test (ubuntu-latest, 3.11)`
- `test (ubuntu-latest, 3.12)`
- `test (macos-latest, 3.8)`
- `test (macos-latest, 3.9)`
- ... (all matrix combinations)

**Recommendation**: Select at least:
- `test (ubuntu-latest, 3.11)` (main test platform)
- `lint` (code quality)

Or select all test matrix combinations for maximum coverage.

### From `lint.yml`:
- `lint`

---

## Workflow for Developers

Once branch protection is enabled:

### Creating a PR:

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and commit
3. Push: `git push -u origin feature/my-feature`
4. Create PR on GitHub
5. **Wait for checks** ⏳
   - Tests run
   - Linting runs
6. **Checks pass** ✅
   - Merge button becomes available
7. **Checks fail** ❌
   - Merge button is disabled
   - Fix issues and push new commit
   - Checks run again

### Merge Options:

With branch protection, you can choose:
- **Squash and merge** (recommended) - Combines all commits into one
- **Rebase and merge** - Keeps individual commits
- **Merge commit** - Creates a merge commit (only if linear history is disabled)

---

## Quick Setup Checklist

- [ ] Go to Settings → Branches
- [ ] Add branch protection rule for `main`
- [ ] ✅ Require pull request before merging
- [ ] ✅ Require status checks to pass
- [ ] Add status checks: `test` and `lint`
- [ ] ✅ Require branches to be up to date
- [ ] ✅ Require linear history
- [ ] ✅ Do not allow bypassing
- [ ] Add exception for `github-actions[bot]`
- [ ] Save changes

---

## Testing Branch Protection

### Create a test PR:

1. Create a test branch:
   ```bash
   git checkout -b test-branch-protection
   echo "# Test" >> TEST.md
   git add TEST.md
   git commit -m "Test branch protection"
   git push -u origin test-branch-protection
   ```

2. Create PR on GitHub

3. Check that:
   - ✅ Tests run automatically
   - ✅ Lint runs automatically
   - ⏳ Merge button is disabled until checks pass
   - ✅ Merge button enables after checks pass

4. Delete test PR and branch

---

## Advanced: Rulesets (GitHub Enterprise)

If you have GitHub Enterprise, you can use **Rulesets** instead of branch protection rules:

1. Settings → Rules → Rulesets
2. New ruleset → New branch ruleset
3. Target: `main` branch
4. Rules:
   - Require status checks
   - Require pull request
   - Block force pushes

Rulesets are more flexible and powerful than branch protection rules.

---

## Troubleshooting

### Problem: "Merge" button is always disabled

**Solution**: Check that required status checks have run at least once. If workflows haven't run yet, GitHub won't show them as available checks.

### Problem: Bot can't push version bumps

**Solution**: Add `github-actions[bot]` to bypass list in branch protection settings.

### Problem: Can't see status checks to select

**Solution**:
1. Push the CI/CD branch first
2. Let workflows run
3. Come back and add the checks

### Problem: Too many required checks (test matrix)

**Solution**: Instead of requiring every matrix combination, require just one or two key platforms:
- `test (ubuntu-latest, 3.11)`
- `lint`

---

## Recommended Minimal Setup

For a small project, require:
- ✅ Pull request before merging
- ✅ Status checks: `test (ubuntu-latest, 3.11)` + `lint`
- ✅ Branches up to date
- ✅ Linear history

This ensures quality without being too restrictive.

---

## Visual Guide

### Before Branch Protection:
```
Developer → Commit → Push to main ✅ (Anyone can push directly)
```

### After Branch Protection:
```
Developer → Commit → Push to feature branch → Create PR
                                                  ↓
                                           Tests run ⏳
                                                  ↓
                                           Tests pass ✅
                                                  ↓
                                           Merge to main ✅
```

### If Tests Fail:
```
Developer → Commit → Push to feature branch → Create PR
                                                  ↓
                                           Tests run ⏳
                                                  ↓
                                           Tests fail ❌
                                                  ↓
                                         Merge blocked 🚫
                                                  ↓
                                           Fix code + Push
                                                  ↓
                                           Tests run again ⏳
```

---

## Additional Resources

- [GitHub Docs: Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub Docs: Required Status Checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)
