"""Build a PR title and body from commit subjects when git-cliff found no
conventional-commit history to render (Method 2 fallback for
.github/workflows/pr-description.yml).

Reads the files the workflow's "Gather PR context" step already wrote:
/tmp/commits.txt (subjects, newest first), /tmp/first_subject.txt (best
title candidate), /tmp/diff_stat.txt. Writes /tmp/pr_title.txt and
/tmp/pr_body.txt on success; the "Update PR" step applies them only when
this script exits 0.
"""

import re

commits = [line.strip() for line in open("/tmp/commits.txt") if line.strip()]
if not commits:
    raise SystemExit("no commits to summarize")

first_subject = open("/tmp/first_subject.txt").read().strip() or commits[0]
title_body = re.sub(r"^[a-z]+(\([^)]+\))?!?: ", "", first_subject)
title = (title_body[:1].upper() + title_body[1:])[:70] if title_body else first_subject[:70]
open("/tmp/pr_title.txt", "w").write(title)

diff_stat = open("/tmp/diff_stat.txt").read().strip()
lines = ["## Changes", ""]
lines += [f"- {c}" for c in commits]
if diff_stat:
    lines += ["", "## Diffstat", "", "```", diff_stat, "```"]
open("/tmp/pr_body.txt", "w").write("\n".join(lines) + "\n")
