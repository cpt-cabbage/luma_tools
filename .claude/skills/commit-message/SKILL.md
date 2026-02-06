---
name: commit-message
description: Generate a well-formatted git commit message and commit the changes
user-invocable: true
---

# Generate Commit Message and Commit

Generate a commit message for the current changes and create the commit.

## Instructions

1. Run `git status` to see all changed/untracked files (never use -uall flag)
2. Run `git diff --stat` to see changed files summary
3. Run `git diff HEAD` to see the full diff (or read from persisted output if large)
4. Analyze the changes and categorize them by area/module
5. Stage all relevant files with `git add` (add specific files by name, not `git add -A`)
6. Create the commit using a HEREDOC for the message (see Commit Format below)
7. Run `git status` after commit to verify success

## Commit Format

Use a HEREDOC to pass the commit message to avoid formatting issues:

```bash
git commit -m "$(cat <<'EOF'
<Brief summary line - imperative mood, ~50 chars>

<Section 1 - e.g., "Canvas Tab:">
- <Change 1>
- <Change 2>

<Section 2 - e.g., "Bug Fixes:">
- <Change 1>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

## Guidelines

- Summary line: imperative mood ("Add feature" not "Added feature"), ~50 chars
- Group changes by module/area (e.g., "Canvas Tab:", "Gallery:", "Core:")
- Use bullet points for individual changes
- Be specific but concise - focus on WHAT changed and WHY
- Skip trivial formatting/whitespace changes
- For deleted files, mention what was removed and why
- Do NOT commit files that likely contain secrets (.env, credentials.json, etc.)
- Always include the Co-Authored-By line at the end
- Do NOT push to remote unless explicitly asked
