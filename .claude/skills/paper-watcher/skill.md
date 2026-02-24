---
name: paper-watcher
description: Track research papers and check for code releases and ComfyUI support
user-invocable: true
---

# Paper Watcher

Track research papers, check if their code/GitHub repos are available, and detect ComfyUI custom node support.

## Arguments

The user passes an action as the argument:

- `add <url> [name]` - Add a paper link to the watchlist (optional friendly name)
- `remove <url or name>` - Remove a paper from the watchlist
- `list` - List all tracked papers with their last known status
- `check` - Check all papers for code availability and ComfyUI support
- `check <url or name>` - Check a specific paper only
- `discover` - Scan curated sources for new papers not yet in the watchlist

If no argument is given, default to `check` (check all papers).

## Storage

The watchlist is stored in `.claude/paper_watchlist.json` at the project root. The format is:

```json
{
  "papers": [
    {
      "url": "https://arxiv.org/abs/2401.12345",
      "name": "Paper Title or User Label",
      "added": "2026-02-08",
      "last_checked": "2026-02-08",
      "status": {
        "code_available": true,
        "github_url": "https://github.com/author/repo",
        "comfyui_support": "none|in_progress|available",
        "comfyui_url": "https://github.com/someone/comfyui-paper-nodes",
        "license": "Apache-2.0",
        "commercial_ok": true,
        "license_issues": null,
        "notes": "Any relevant details"
      }
    }
  ]
}
```

## Instructions

### For `add`

1. Read the current `.claude/paper_watchlist.json` (create if it doesn't exist with `{"papers": []}`)
2. Check the URL isn't already in the list (match by URL)
3. If the URL is an arXiv link, use WebFetch to grab the paper title from the page
4. Add the entry with `added` date set to today, `last_checked` as null, `status` as empty
5. Write the updated JSON back
6. Report what was added

### For `remove`

1. Read the watchlist
2. Find the paper by URL match or name substring match (case-insensitive)
3. If multiple matches, show them and ask the user to be more specific
4. Remove the entry and write back
5. Report what was removed

### For `list`

1. Read the watchlist
2. Display a formatted table with columns: Name, URL, Last Checked, Code Available, ComfyUI Support
3. Use markdown table format
4. If the list is empty, tell the user and suggest using `add`

### For `check`

This is the core functionality. For each paper in the watchlist (or the specified one):

**Skip rule:** If a paper's `last_checked` date is today, skip it entirely — do not re-check or re-report it. Only check papers that haven't been checked today. If ALL papers were already checked today, report "All papers already checked today. Use `check <name>` to force-recheck a specific one."

#### Step 1: Identify the paper and find code

**If the URL is an arXiv link:**
- Use WebSearch to search for: `"<paper title>" OR "<arxiv id>" github code`
- Also search: `"<arxiv id>" site:paperswithcode.com`
- Look for official GitHub repos, Papers With Code entries, or author implementations
- Extract the GitHub URL if found

**If the URL is already a GitHub link:**
- Use WebFetch to check if the repo exists and note its description/readme summary
- Mark `code_available: true`

**If the URL is a project page:**
- Use WebFetch to scan for GitHub links on the page
- Follow the first relevant GitHub link found

#### Step 2: Check license and commercial viability

For each paper that has code available (real code, not placeholder):

- Check the repo's LICENSE file (via WebFetch or from the repo page) to identify the license type
- Check if the code depends on non-commercial models or weights (e.g., FLUX.1-dev is non-commercial, Stable Diffusion models vary, some HuggingFace weights are research-only)
- Check the paper or README for usage restrictions

Classify commercial viability:
- **`commercial_ok: true`** — Permissive license (Apache-2.0, MIT, BSD) AND no non-commercial model dependencies
- **`commercial_ok: false`** — Non-commercial license (CC BY-NC, research-only) OR depends on non-commercial models/weights
- **`license`** — The SPDX license identifier (e.g., "Apache-2.0", "MIT", "CC-BY-NC-SA-4.0") or "unknown" if not found
- **`license_issues`** — null if no issues, otherwise a brief string explaining the problem (e.g., "Code is Apache-2.0 but depends on FLUX.1-dev (non-commercial)", "CC BY-NC-SA 4.0 — non-commercial only")

#### Step 3: Check for ComfyUI support

For each paper that has a GitHub repo identified:

- **Search 1:** WebSearch for `"<paper name>" comfyui custom node`
- **Search 2:** WebSearch for `"<repo name>" comfyui`
- **Search 3:** Check the GitHub repo itself (via WebFetch on the repo page) for mentions of "comfyui" or "ComfyUI" in the README

Classify ComfyUI support as:
- **`available`** - A working ComfyUI custom node package exists (link it)
- **`in_progress`** - There are WIP repos, open issues requesting ComfyUI support, or forks working on it
- **`none`** - No ComfyUI integration found

#### Step 4: Update and report

1. Update each paper's `status` and `last_checked` in the watchlist JSON
2. Write the updated watchlist
3. Present results as a compact colored summary (NOT per-paper details):

```
## Paper Watcher Report — <date>

### Code + ComfyUI Available
🟢 **Paper Name** — [repo](github_url) — ComfyUI: [node](comfyui_url)
(repeat for each paper with code AND comfyui support)

### Code Available
🔵 **Paper Name** — [repo](github_url) — <one-line note>
(repeat for each paper with code but no comfyui)

### Placeholder / Coming Soon
🟡 **Paper Name** — repo exists but no code yet
(repeat for each paper with a placeholder repo)

### No Code Yet
🔴 **Paper Name** — no repo found
(repeat for each paper with no repo at all)

### Commercial Usage Warnings
⚠️ **Paper Name** — license issue description
(repeat for each paper where commercial_ok is false. Only show this section if there are issues.)

---
**Summary:** X checked · X code available · X ComfyUI · X no code · X commercial issues
```

**Rules for the report:**
- Group papers by status tier using the colored circles above
- One line per paper, keep it short — name + repo link + brief note
- Do NOT show full URLs inline, use markdown links
- Do NOT repeat the paper URL (user already knows it from the watchlist)
- If a section is empty, skip it entirely
- Sort papers alphabetically within each section

### For `discover`

Scan curated discovery sources for new papers that match the studio's interests and aren't already tracked.

#### Step 1: Load the existing watchlist

Read `.claude/paper_watchlist.json` and collect all tracked URLs and paper names into a known set for deduplication.

#### Step 2: Define topic interests

The studio focuses on these areas (inferred from the existing watchlist):
- **Video generation** — text-to-video, image-to-video, camera control, motion
- **Image generation & editing** — diffusion models, instruction-based editing, text rendering
- **3D / 4D reconstruction** — NeRF, Gaussian splatting, 4D synthesis, novel view synthesis
- **Character & motion** — motion capture, human animation, rigging, pose estimation
- **Audio-video** — synchronized audio generation with video
- **Depth & scene understanding** — depth estimation, inverse rendering, lighting
- **Multimodal models** — vision-language models relevant to generation pipelines

#### Step 3: Check discovery sources

Run these in order. For each source, extract paper titles, URLs, and brief descriptions.

**Source 1 — HuggingFace Papers (trending):**
- WebFetch `https://huggingface.co/papers` — extract the list of trending paper titles and arXiv links shown on the page

**Source 2 — Papers With Code (latest computer vision):**
- WebFetch `https://paperswithcode.com/latest` — extract recently added papers with code, focusing on CV/generation tasks

**Source 3 — Targeted recent paper searches:**
Run these WebSearches to catch papers that may not be trending yet:
- `site:arxiv.org 2026 video generation camera control`
- `site:arxiv.org 2026 image editing diffusion transformer`
- `site:arxiv.org 2026 4D generation gaussian splatting`
- `site:arxiv.org 2026 motion capture human animation`

#### Step 4: Filter and score candidates

For each discovered paper:
1. **Skip** if its URL or title closely matches anything already in the watchlist (case-insensitive substring match on title, exact match on URL)
2. **Skip** if it's clearly off-topic (NLP-only, medical, robotics control theory, etc.)
3. **Score relevance** — prefer papers that:
   - Match multiple topic areas from Step 2
   - Have a project page or GitHub link already (higher chance of imminent code release)
   - Come from known labs (Adobe, NVIDIA, Google, Meta, ByteDance, Alibaba/Qwen, Tencent, Kuaishou, etc.)
   - Are less than 60 days old

#### Step 5: Present candidates

Do NOT automatically add papers to the watchlist. Present candidates for the user to review:

```
## Paper Watcher Discover — <date>

### Highly Relevant
**[Paper Title](url)** — one-sentence description. [code/no code]

### Possibly Relevant
**[Paper Title](url)** — one-sentence description.

---
Sources checked: HuggingFace Papers, Papers With Code, arXiv search
New candidates: X · Already tracked: X skipped
```

**Rules:**
- Group into "Highly Relevant" (directly matches 2+ topic areas or is from a top lab) and "Possibly Relevant" (tangential but interesting)
- Max 15 candidates total — be selective, quality over quantity
- One line per candidate: title as link + one sentence + note if code/repo already exists
- End with a tip: `To add any of these: /paper-watcher add <url>`
- If nothing new is found, say so clearly

## Important Notes

- Use WebSearch and WebFetch for all lookups - do NOT guess URLs
- When a GitHub repo is found, always store the URL so future checks can go directly to it
- Be conservative with "available" status - only mark ComfyUI as available if there's a real, installable custom node package
- For "in_progress", it's OK to include forks, issues, or discussions that show interest
- Always preserve existing data when writing the JSON (don't drop fields)
- Rate limit awareness: if checking many papers, proceed sequentially to avoid overwhelming web tools
