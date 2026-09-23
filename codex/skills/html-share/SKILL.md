---
name: html-share
description: Share a local static HTML page or prebuilt frontend through a public URL. Use when the user asks to share, publish, or host a page without a backend or Git-based deployment, not when they ask only how static hosting works.
---

# HTML Share

Publish prebuilt static content through a simple hosting CLI while keeping source files, credentials, and production state safe.

## Scope

- Accept either one HTML file or a directory whose root contains `index.html`.
- For a source project, run its existing build first and publish only the documented static output directory.
- Honor a hosting provider named by the user. Otherwise use a manual Netlify CLI deploy as the default simple target.
- Do not connect Git, add serverless functions, configure continuous deployment, or change domains unless the user asks.

## Prepare

1. Resolve the exact source path and whether the user wants a temporary preview URL or the production site URL.
2. Inspect the source for secrets, private files, local filesystem links, and unexpected files. Never upload a repository root merely because it contains an HTML file.
3. Create a temporary staging directory with `mktemp -d`, then run `uv run --script scripts/prepare-static-site.py <source> <staging/site>`. The script converts a single HTML file to `index.html`, rejects common credential files and symlinks, and refuses obvious local-only URLs.
4. Review the staged file list and size before any network mutation. Do not include `.git`, `.env*`, credentials, raw logs, or unrequested source files.

## Default Netlify target

- Prefer an installed `netlify` command. If it is absent, ask before installing Netlify CLI or invoking `npx netlify-cli@latest` because that downloads executable code.
- Check authentication with `netlify status`. If login is needed, run `netlify login`; it opens Netlify in the user's browser and stores the token in Netlify's global configuration. Never print, copy, or persist that token in the project.
- The first `netlify deploy` may prompt to select an existing site or create a new one. Keep the generated `.netlify` state in the temporary staging directory, not in the user's source tree.
- For an already known project, prefer `--site <project-id-or-name>` over modifying source-tree configuration.

## Publish

Before the first upload, state the staged path, file count, target provider and site if known, and whether the action is preview or production. Obtain explicit authorization for the external upload unless the user has already named the target and said to publish it now.

For the default Netlify target:

- Preview: `netlify deploy --dir=<staged-directory>`
- Production: `netlify deploy --dir=<staged-directory> --prod`

Default to a preview when the user asks to share, preview, or test. Use `--prod` only when the user explicitly asks for production, the main URL, or a public final deployment. Do not use `--allow-anonymous` unless the user specifically wants an ephemeral site that must be claimed within one hour.

After publishing, capture the returned URL, verify that it serves successfully, and confirm that the expected page title or another stable marker is present. Report the URL, preview/production status, provider, and any remaining manual action. Stop after two failed publishing attempts and report the exact blocker rather than creating additional sites.

## References

- Netlify CLI setup, authentication, and manual deploy behavior: https://docs.netlify.com/api-and-cli-guides/cli-guides/get-started-with-cli/
- Netlify manual and drag-and-drop deploys: https://docs.netlify.com/deploy/create-deploys/
