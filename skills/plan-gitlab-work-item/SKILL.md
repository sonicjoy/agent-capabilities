---
name: plan-gitlab-work-item
description: >-
  Create and keep a GitLab work item in sync for any Colossus task. Use when
  starting, continuing, or finishing Colossus work, when creating or executing
  a plan, or when the user says remember to track work with a GitLab work item.
---

# Plan tracks a GitLab work item

For any Colossus task we work, create a GitLab work item and keep it in sync with the agent's progress. Skipping this is a process bug. This covers every Colossus task, not only planned work.

Follow `gitlab-issues` for `glab` auth and the browser fallback. Status is the GitLab built-in status field (`To do` → `In progress` → `Done`), not a label. Set it with GraphQL `workItemUpdate` + `statusWidget` when `glab issue update` cannot. Never `Closes`, `Fixes`, or `Resolves`. Commits follow the general commit-regularly rule, not this skill.

## When

- A Colossus task starts: create the work item if none exists for this task, before or as the work starts.
- The task or plan changes: comment what changed, and rewrite the description when Why, What, Details, Scope, or Acceptance changed.
- Implementation starts: status `In progress` and a comment.
- An MR opens, a slice stops, or the approach changes: comment. Stay `In progress`.
- The work is verified done: comment the evidence, then status `Done`.

One work item per task. Do not open a second one. Put the work-item URL in the plan when there is one. Attach the plan file to that work item, and refresh the attachment whenever the plan changes. A repo path alone is not enough while the file is only local.

## Description

Every work item body uses these headings, in this order. Write for a person. Short paragraphs and short lists. No sixth heading.

1. **Why** — the problem and who feels it.
2. **What** — the change, in one or two sentences.
3. **Details** — evidence, the rule, and the pieces of work.
4. **Scope** — in, and out.
5. **Acceptance** — how we will know it is done.

Same shape when the plan changes and the description is rewritten. Progress notes stay the short **Plan —** comment below.

## Where

Open it on the GitLab project for the repo being changed. Use that repo's host (`gitlab.com` or `gitlab.colossusbets.com`). Assign it to the user you are working for (their GitLab username).

## Comment

```markdown
**Plan — <gate>**
- Plan: <name>
- What changed: <one or two lines>
- Status: <To do | In progress | Done>
- Next: <what is blocked or what happens next>
```
