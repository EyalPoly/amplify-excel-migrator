# Workflow
- Be sure to typecheck when you're done making a series of code changes
- Run tests after making code changes to ensure nothing is broken
- When writing tests, ensure you cover edge cases and potential failure points
- Strive for clarity and simplicity in your code; avoid unnecessary complexity
- Refactor code when you see opportunities to improve structure or readability
- Update README to reflect any changes made to functionality or usage

# Versioning (see .github/workflows/publish.yml)
- On PR merge to main, CI auto-bumps the PATCH version, tags, and publishes to PyPI. Never bump the patch manually — CI owns it.
- For a feature (minor) or breaking change (major), bump `version` in setup.py by hand AND include `[skip bump]` in the PR title or a commit message, so CI doesn't add an extra patch on top.

# Comments
- Only add comments and docstrings when they are truly needed to explain why something is done a certain way, not what is being done. Code should be self-explanatory as much as possible.

# Decision-Making
- Never make any claims about code before investigating unless you are certain—give grounded and hallucination-free answers.

# Workflow for Complex Tasks
Follow the "Explore, Plan, Code" approach:

## Step 1 - Explore
Read and understand the relevant files and directories. Trace how the existing functionality works. DO NOT write any code yet.

## Step 2 - Plan
Based on your exploration, think deeply about the implementation. Create a plan that includes:
- The approach and architecture
- Edge cases and potential issues
- Files that need to be created or modified

## Step 3 - Implement
Implement the solution following your plan. Verify each step as you go and adjust the plan if needed.

