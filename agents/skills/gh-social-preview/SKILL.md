---
name: gh-social-preview
description: Create a GitHub repository's social preview image from synthetic data. Use when the user asks to make, redraw, or update a GitHub repository's social preview or its link card.
---

# GitHub Social Preview

Make the image people see when a GitHub repository link is shared (GitHub, X, Slack, Telegram).

## Size and safe area

- Canvas 1280×640 px (2:1); GitHub accepts at least 640×320, but 1280×640 displays best. PNG under
  1 MB (GitHub's limit); JPG or GIF only when PNG can't fit.
- Keep a 40 pt border free of anything important, as GitHub's template marks it: at 1280×640 that
  is an 80 px margin on every side, so text, logo and the key part of a screenshot stay inside the
  1120×480 area from (80, 80) to (1200, 560). Background, gradients and decorative shapes may run to
  the edges.
- GitHub's template: Settings → General → Social preview → Download template
  (`https://github.com/<owner>/<repo>/settings/og-template`, needs login).

## Content

- Left: the project name as a big wordmark and a tagline of at most two lines, the same as the
  readme's tagline. Optionally a row of 3–4 icons with one-word labels for the main concepts.
- Right: what the tool looks like (a terminal window or app screenshot), cropped to the part that
  explains it; no shell prompt with branch names, user names or local paths.
- Use only synthetic data in screenshots (`work/web-app`, `oss/cli-tool`, plausible round numbers):
  never the user's real projects, costs, tokens or paths, since the image is public. Reuse a
  synthetic screenshot the repo already has (e.g. `docs/images/*.svg`) when there is one.
- Keep the project's current facts: name, language, what it reads or supports, the main command.
  An outdated command or install method on the card is worse than none.

## Build

- Compose an SVG (wordmark, tagline, icons, embedded screenshot) and render it to PNG at exactly
  1280×640 with a headless browser or `rsvg-convert`; keep the source SVG outside the repo unless
  the user asks to commit it.
- Check the PNG at full size and scaled to ~600 px wide (how X and Slack show it): text readable,
  nothing important inside the 80 px margin, nothing cut.
- Deliver the PNG and its source with a one-line note on how to regenerate. Uploading is manual:
  the repository's Settings → General → Social preview → Edit; there is no API for it.
