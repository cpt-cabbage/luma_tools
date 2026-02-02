---
name: commit-message
description: Generate a well-formatted git commit message based on staged/unstaged changes
user-invocable: true
---

# Generate Commit Message

Generate a commit message for the current changes in the repository.

## Instructions

1. Run `git diff --stat` to see changed files summary
2. Run `git diff HEAD` to see the full diff (or read from persisted output if large)
3. Analyze the changes and categorize them by area/module
4. Generate a commit message following this format:

```
<Brief summary line - what was done, imperative mood, ~50 chars>

<Section 1 - e.g., "Canvas Tab:">
- <Change 1>
- <Change 2>

<Section 2 - e.g., "Bug Fixes:">
- <Change 1>

<Optional: Cleanup/Refactoring section>

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Guidelines

- Summary line: imperative mood ("Add feature" not "Added feature"), ~50 chars
- Group changes by module/area (e.g., "Canvas Tab:", "Gallery:", "Core:")
- Use bullet points for individual changes
- Be specific but concise - focus on WHAT changed and WHY
- Skip trivial formatting/whitespace changes
- For deleted files, mention what was removed and why
- Always include the Co-Authored-By line at the end

## Output

Present the commit message in a code block so the user can easily copy it.
