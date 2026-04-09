---
name: memory
description: Markdown-on-disk persistent memory store. Save reusable experiences (email templates, pipeline recipes, bug fixes, prompts, JIRA templates, devops library notes, AI patterns, successful QA dialogues) to `.agent-memory/<category>/<slug>.md` and recall them in future conversations so the user never has to solve the same problem twice. **MUST be used when** the user says 记住 / 帮我记住 / 记住它 / 下次也这样做 / save this / remember this / save it as a template / this worked, keep it — and **MUST be used proactively** at the START of every new task to search for prior experiences before doing the work.
---

# Memory Skill

A markdown-on-disk persistent memory store. Each memory is one file:

```
.agent-memory/<category>/<slug>.md
```

with YAML-style frontmatter for metadata and a markdown body for content.
The directory is created lazily under the current working directory, so
memories are naturally scoped to the project / workspace where the agent
is running. Drive everything through one CLI:

```
python skills/memory/memory.py <subcommand> [args]
```

## Why markdown instead of a database

- The user can read, grep, and hand-edit memories in any editor.
- They survive moving the project — they're just files in a hidden dir.
- They're trivially version-controllable if the user wants to commit them.
- Recall is just plain text search — no schema, no migrations.

## Two core flows

### A. Recall — at the START of every new task, BEFORE doing the work

This is the part the agent forgets most easily. **Always run a search
first** when the user's request looks like something that might have a
reusable template or recipe.

```
# General search
python skills/memory/memory.py search "<key terms>"

# Better, when you know the bucket — narrow by category
python skills/memory/memory.py search "客户致歉" --category email_customer
python skills/memory/memory.py search "airflow retry" --category pipeline
python skills/memory/memory.py search "circular import" --category bug_fix
```

If a relevant hit is found, fetch the full record:

```
python skills/memory/memory.py get <id>
```

This bumps the memory's `usage_count` so frequently-used patterns float to
the top in `top_used` later. Then **tell the user**: "I found a prior
experience for this — applying the same pattern" before doing the work.

If multiple candidates exist, briefly list the titles and confirm which to
apply. If nothing relevant is found, just proceed normally — never invent a
match.

### B. Save — when the user signals "remember it"

Trigger phrases (any language):

- **Chinese**: "记住", "记住它", "帮我记住", "下次也这样做", "把这个存下来"
- **English**: "save this", "remember this", "save it as a template",
  "this worked, keep it", "next time do the same"

After the problem is solved, classify the experience and call `save`.

| Problem solved                       | category         |
|--------------------------------------|------------------|
| Pipeline / CI / data flow            | `pipeline`       |
| Customer-facing email                | `email_customer` |
| Internal team / stakeholder email    | `email_internal` |
| JIRA / ticket template               | `jira_template`  |
| Bug fix recipe                       | `bug_fix`        |
| Devops / infra library usage         | `devops_lib`     |
| AI prompt / model usage              | `ai_knowledge`   |
| Successful QA dialogue pattern       | `qa_experience`  |
| Anything else                        | `general`        |

The memory should capture **enough that a future-you can replay the path**:

- `--title` — short, descriptive (becomes the filename slug)
- `--problem` — the original symptom / user issue
- `--context` — the **key dialogue turns** that led to the breakthrough
  (what was tried in order, which one worked)
- `--solution` — the concrete answer to paste back next time (the email
  body, the code, the command, the prompt)
- `--pattern` — the **reusable strategy** distilled from the experience
  (the most valuable field — write it like a rule, not a story)
- `--tags` — comma-separated keywords for filtering

## Subcommands

| Subcommand          | Purpose                                          |
|---------------------|--------------------------------------------------|
| `save`              | Save / update a memory (idempotent on title)     |
| `get`               | Fetch a memory by id and bump its usage counter  |
| `search`            | Full-text search by query / category / tag      |
| `list`              | List memories grouped by category                |
| `delete`            | Remove a memory                                  |
| `categories`        | Count memories per category                      |
| `top_used`          | Most-frequently-recalled memories                |
| `scratchpad_write`  | Write a named short-lived scratchpad             |
| `scratchpad_read`   | Read a named scratchpad                          |
| `scratchpad_append` | Append to a scratchpad                           |

Run `python skills/memory/memory.py <subcommand> --help` for full flags.

## Markdown format

Each memory file looks like this on disk:

```markdown
---
title: airflow dag retry storm fix
category: pipeline
tags: [airflow, retry, pipeline]
created_at: 2026-04-10 12:34:56
updated_at: 2026-04-10 12:34:56
usage_count: 0
---

# airflow dag retry storm fix

## Problem

DAG keeps retrying failed tasks indefinitely after upstream API outage.

## Context

Tried: 1) bumping retry_delay (no), 2) max_active_runs=1 (no),
3) on_failure_callback to break the loop (yes).

## Solution

Set on_failure_callback that calls dag.set_state(FAILED) after N retries.

## Reusable Pattern

Airflow's built-in retry has no circuit breaker — implement one in
on_failure_callback.
```

The user can `cat`, `rg`, or open these in any editor. There is no
database — the filesystem **is** the database.

## Calling patterns the agent should use

**Recall before starting a new task**

```
python skills/memory/memory.py search "airflow retry"
python skills/memory/memory.py search "客户致歉" --category email_customer
python skills/memory/memory.py get airflow-dag-retry-storm-fix
```

**Save after a non-trivial problem is solved**

For short fields, pass them inline:

```
python skills/memory/memory.py save \
  --title "airflow dag retry storm fix" \
  --category pipeline \
  --problem "DAG keeps retrying failed tasks indefinitely after upstream API outage" \
  --context "Tried: 1) bumping retry_delay (no), 2) max_active_runs=1 (no), 3) on_failure_callback to break the loop (yes)" \
  --solution "Set on_failure_callback that calls dag.set_state(FAILED) after N retries" \
  --pattern "Airflow's built-in retry has no circuit breaker — implement one in on_failure_callback" \
  --tags "airflow,retry,pipeline"
```

For long fields (especially the solution body of an email or a multi-line
code block), write each section to a temp file first and use the `--*-file`
flags — much safer than wrestling with shell quoting:

```
# write /tmp/problem.txt, /tmp/context.txt, /tmp/solution.txt, /tmp/pattern.txt
python skills/memory/memory.py save \
  --title "customer apology for outage" \
  --category email_customer \
  --problem-file /tmp/problem.txt \
  --context-file /tmp/context.txt \
  --solution-file /tmp/solution.txt \
  --pattern-file /tmp/pattern.txt \
  --tags "outage,apology,customer"
```

You can also pipe the largest field via stdin (defaults to `solution`):

```
cat email-template.md | python skills/memory/memory.py save \
  --title "customer apology for outage" \
  --category email_customer \
  --pattern "Lead with the impact statement, then the timeline, then the fix" \
  --stdin --stdin-field solution \
  --tags "outage,apology,customer"
```

## Two worked examples (the canonical workflow)

### Example 1 — saving an email template

User asked you to draft a customer apology for a 30-minute outage. You
wrote the email, the user replied "完美，记住这个模版":

```
python skills/memory/memory.py save \
  --title "customer apology for outage" \
  --category email_customer \
  --problem "Need to apologize to customers for a service outage and explain the fix" \
  --solution-file /tmp/email-body.md \
  --pattern "Open with impact + timeframe, give concrete root cause in plain English, end with prevention measures and contact channel" \
  --tags "outage,apology,customer,email-template"
```

**Next conversation**, user says "用上次那个客户致歉模版写一封关于今天 30 分钟
服务中断的邮件":

1. `python skills/memory/memory.py search "客户致歉" --category email_customer`
2. The result list shows `customer-apology-for-outage` — you recognize it.
3. `python skills/memory/memory.py get customer-apology-for-outage`
   (this prints the full markdown, including the template body, and bumps
   the usage counter).
4. Take the `## Solution` section as your template, fill in the new
   specifics (today's incident, duration, root cause), reply with the
   drafted email — and tell the user "I'm reusing the saved template
   `customer-apology-for-outage`".

### Example 2 — saving a debugging recipe

User had a stuck Airflow DAG retrying forever. You tried prompt A, then B,
then C, and the third one fixed it. User says "帮我记住它":

```
python skills/memory/memory.py save \
  --title "airflow dag retry storm fix" \
  --category pipeline \
  --problem "DAG keeps retrying failed tasks indefinitely after upstream API outage" \
  --context "Tried: 1) bumping retry_delay (no effect), 2) max_active_runs=1 (no effect), 3) on_failure_callback to break the loop (worked)" \
  --solution "Set on_failure_callback that calls dag.set_state(FAILED) after N retries" \
  --pattern "Airflow's built-in retry has no circuit breaker — implement one in on_failure_callback" \
  --tags "airflow,retry,pipeline,debugging"
```

**Next conversation**, user mentions a stuck Airflow DAG. Before doing
anything, run `search "airflow retry"`. The recall returns this memory,
you `get` it, and you propose the same fix without re-deriving it.

## Other rules of thumb

- Don't wait for an explicit "remember this" if the user just nailed a
  non-trivial problem and is clearly pleased — proactively ask "want me to
  save this as a reusable pattern?" before moving on.
- When updating a memory (same `--title` and `--category`), `created_at`
  and `usage_count` are preserved automatically — only `updated_at` and
  the body fields change.
- Use `top_used` occasionally to see which memories the user actually
  reaches for — those are the patterns worth refining.
- Use `scratchpad_*` for short-lived, current-task-only notes (planning a
  refactor, tracking progress on a 5-step task). **Scratchpads are NOT
  cross-session memory** — for that, use `save`.
- File slugs are derived from the title; saving with the same title and
  category updates the existing memory rather than creating a duplicate.
- If you see `.agent-memory/` in `.gitignore`, the user is keeping memories
  local. If it's tracked, the user wants to share them across machines —
  respect the existing setup.

## Mental model

Memory is the agent's **long-term brain** for this user / project. The
whole point is that the user shouldn't have to solve the same problem
twice — and you shouldn't have to either. Every recalled memory is a turn
the user *didn't* have to type. Every saved memory is a future
conversation that just got faster.
