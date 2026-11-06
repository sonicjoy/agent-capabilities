---
name: gitlab-issues
description: Manage GitLab issues and merge requests using glab CLI (merge requests via `glab api`), with web browser (MCP) as fallback when the CLI cannot complete the task. Use when the user mentions GitLab issues, wants to start work on an issue, update issue status, add labels, open a merge request, or follow the GitLab workflow.
---

# GitLab Issue Management

Manage GitLab issues via `glab` CLI. **Prefer glab for speed and repeatability.** When glab cannot authenticate, errors on create/update, or lacks a needed field for this GitLab version, **fall back to the web UI via the IDE browser MCP** (see below).

## GitLab Instance

- **URL:** https://gitlab.colossusbets.com/
- **Host (for glab):** `gitlab.colossusbets.com`
- **Token:** use the `GITLAB_TOKEN` environment variable. Set it before glab auth or ensure it is already set in the environment.

## Login if Not Authenticated

Before running glab issue/PR commands:

1. **Check auth:** `glab auth status`
2. **If `gitlab.colossusbets.com` is missing, shows "No token found", or "could not authenticate":**
   - Ensure `GITLAB_TOKEN` is set (e.g. `$env:GITLAB_TOKEN` in PowerShell).
   - Log in using the token from env:
     - **PowerShell:** `$env:GITLAB_TOKEN | glab auth login --hostname gitlab.colossusbets.com --stdin`
     - **Bash:** `echo "$GITLAB_TOKEN" | glab auth login --hostname gitlab.colossusbets.com --stdin`
   - Token must have at least `api` and `write_repository` scopes.
3. **If the repo’s git remote uses a different host** (e.g. `gitlab-shell.colossusbets.com`), still auth with `--hostname gitlab.colossusbets.com` (API host). For issue create/update, use `-R https://gitlab.colossusbets.com/group/repo` and `GITLAB_HOST=gitlab.colossusbets.com` so glab uses the configured host.
4. **Proxy errors** (e.g. `proxyconnect tcp: 127.0.0.1:...`): unset `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` in that shell when they should not apply to GitLab.

## When to Use

- User provides a GitLab issue URL
- User wants to start work on an issue
- User mentions updating issue status or labels
- User asks to "follow the GitLab flow"

## Common Commands

### View an Issue

```bash
glab issue view <id>
glab issue view <id> --web  # Opens in browser
```

### Update Labels

```bash
# Add labels
glab issue update <id> --label "Doing"

# Remove labels
glab issue update <id> --unlabel "Doing"

# Add and remove in one command
glab issue update <id> --label "QA Backlog" --unlabel "Doing"
```

### Other Updates

```bash
# Assign
glab issue update <id> --assignee <your-gitlab-username>

# Set milestone
glab issue update <id> --milestone "Sprint 1"

# Update title/description
glab issue update <id> --title "New title"
glab issue update <id> --description "New description"
```

## Merge Requests: use the API, not `glab mr create`

On `gitlab.colossusbets.com`, open merge requests with the REST API through `glab api` from the start. `glab mr create` has exited with no output and created nothing (cbstatsfeed !164, 2026-10-14, glab v1.80.4), while the API call worked first time.

```bash
export GITLAB_HOST=gitlab.colossusbets.com
# Project id and your user id, once per repo/session
glab api "projects/<group>%2F<subgroup>%2F<repo>" | python -c "import sys,json;print(json.load(sys.stdin)['id'])"
glab api user | python -c "import sys,json;print(json.load(sys.stdin)['id'])"

glab api -X POST projects/<project-id>/merge_requests \
  -f source_branch=<branch> -f target_branch=develop \
  -f "title=<title>" -f "description=$(cat mr.md)" \
  -f assignee_id=<user-id> -f "labels=Bug,C#" -f remove_source_branch=true
```

- Confirm it from the returned `web_url` (and `iid`); don't trust a silent exit.
- Write `Refs #<issue>` in the description, never `Closes`/`Fixes`/`Resolves`.
- Push the branch first (`git push -u origin <branch>`); the API does not push.
- The same route works for other writes when glab lags the server: comments with `glab api -X POST projects/<id>/issues/<iid>/notes -f "body=..."`, and the built-in Status field with GraphQL `workItemUpdate` + `statusWidget` (see `plan-gitlab-work-item`).
- File uploads (e.g. attaching a plan) need multipart, which `glab api -F file=@...` does not send: use `curl -H "PRIVATE-TOKEN: $(glab config get token --host gitlab.colossusbets.com)" -F "file=@plan.md" https://gitlab.colossusbets.com/api/v4/projects/<id>/uploads`.

## Issue Workflow

### When Starting Work on an Issue

```bash
glab issue update <id> --label "Doing" --unlabel "Development Backlog"
```

### When Pushing Fix (Ready for QA)

```bash
glab issue update <id> --label "QA Backlog" --unlabel "Doing"
```

## Issue Creation Defaults

When creating new issues for enginelinux project:

```bash
glab issue create --assignee <your-gitlab-username> --label "C#" --title "Issue title" --description "$(cat description.md)"
```

## CbStatsFeed Tech Story Format (Persisted Preference)

When the user asks to create a technical story in `cbstatsfeed`, use this default format unless they override it:

- Parent epic: `Pick'em Bet Builder`
- Labels: `BetBuilder`, `C#`
- Assignee: the user you are working for (their GitLab username)
- Weight: `5`

Description template:

```markdown
## objective
<clear one-paragraph objective>

## scope
- <input source 1>
- <input source 2>
- <processing/build behavior>
- <integration behavior>

## technical notes
- <deterministic/idempotent behavior>
- <error handling and retries>
- <logging and metrics>
- <data validation and conflict handling>

## acceptance criteria
- <functional result 1>
- <functional result 2>
- <operational/reliability result>
- <dedup/idempotency result>
- <diagnostics result>

## out of scope
- <explicit non-goals>
```

For the PropBuilder story pattern, use this responsibility split:
- PropBuilder builds and returns/exposes props
- caller/user publishes to kafka topic `<name to be determined>`

For the Message Router story pattern (Bet Builder pipeline):
- Stats Feeds Services call into Message Router
- Message Router orchestrates PropBuilder for prop construction
- Message Router publishes to Kafka (Kafka Publisher path); PropBuilder does not publish directly

## Extracting Issue ID from URL

GitLab URLs follow: `https://gitlab.colossusbets.com/group/project/-/issues/<id>`

Extract the numeric `<id>` from the URL path.

## Fallback: Web browser (when glab is not enough)

Use the **embedded browser / browser MCP** as a **second-line method** after trying glab. Do not give up after one glab failure—fix auth or flags when possible—but **switch to the browser** when any of these apply:

- **Auth or environment:** `glab auth status` fails, token is missing/invalid, or proxy/hostname fixes do not unblock the API.
- **API vs product surface:** Creating or editing **work items** (parent epic, weight, type) fails or behaves differently than `glab issue create` / `glab issue update` on this instance.
- **Unsupported or unclear CLI:** glab returns an error about an unknown flag, missing resource, or permission; the needed field exists only in the UI.
- **Verify after automation:** Confirm a create actually completed (redirect, issue number) when CLI output is ambiguous.

### URLs (CbStatsFeed on colossusbets GitLab)

- **New work item:** `https://gitlab.colossusbets.com/colossus/c_sharp/cbstatsfeed/-/work_items/new`
- **Existing item:** `https://gitlab.colossusbets.com/colossus/c_sharp/cbstatsfeed/-/work_items/<id>` (or `/-/issues/<id>` depending on routing)

Adjust `group/project` path for other repositories.

### Browser workflow (generic)

1. Navigate to the new-issue or issue URL above.
2. Take a **snapshot** of the page; use refs from the latest snapshot for clicks and fields (refs go stale after navigation or re-renders—**re-snapshot** if a click misses).
3. Fill **title** and **description** (paste markdown); set **assignee**, **labels**, **parent**, **weight**, **milestone** as required.
4. Submit (**Create issue** / **Save changes**). **Wait** for navigation or UI confirmation.
5. **Success check:** URL should leave `/work_items/new` and show something like `/-/work_items/<id>`; capture the **full URL and ID** for the user.
6. If the description shows **literal `\n`** or broken formatting, open **Edit** in the UI and fix the body once.

### MCP tool names

Use whatever browser tools the active IDE exposes (e.g. navigate, snapshot, click, type/fill, wait). In Cursor, the integration is often named like `browser_snapshot`, `browser_click`, etc.; prefer the tool schema in the session over memorized names.
