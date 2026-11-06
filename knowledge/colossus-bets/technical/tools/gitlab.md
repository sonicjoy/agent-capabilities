<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# GitLab Conventions

**Added**: 2026-04-13
**Context**: User clarified the canonical GitLab instance for Colossus work.
**Id**: `gitlab-conventions`

> Colossus GitLab is the self-hosted gitlab.colossusbets.com, not GitLab.com; point glab at that host.

## Colossus self-hosted GitLab

- **Web UI (canonical):** [https://gitlab.colossusbets.com/](https://gitlab.colossusbets.com/) — self-hosted GitLab, **not** GitLab.com.
- **Access:** Sign-in is fronted by **Cloudflare Access** (e.g. Google Workspace), per the login page at that host.
- **Git remotes:** Repositories may use a separate SSH host (e.g. `gitlab-shell.colossusbets.com`) while the browser and API configuration for `glab` should align with the instance you authenticate against (often the same API base as the web URL, depending on admin setup).

For `glab`, ensure the configured host matches this self-hosted instance so API calls (e.g. `glab issue create`) hit `gitlab.colossusbets.com` rather than assuming `gitlab.com`.

Work items for agent tasks: every Colossus task gets one item with Why, What, Details, Scope, and Acceptance, kept in sync as the work moves. See `technical/workflow/workflow.md`.

## Note

GitLab issue workflow is also described in the `gitlab-issues` skill (`skills/gitlab-issues/` in agent-capabilities).
