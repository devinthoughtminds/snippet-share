# Claude Code initial setup

Every developer on snippet-share uses Claude Code with two plugins, Langfuse's docs MCP server and agent skill (section 5) and a backend testing skill (section 6). Both are enabled for this repo only, in [settings.json](settings.json), so they don't affect your other projects.

- **Superpowers** sets the process: design, then plan, then test-first build, then review.
- **Ponytail** keeps each change small: reuse what's already in the codebase and don't add abstractions nobody asked for. It never cuts validation, error handling, security, or accessibility.

## 1. Install the plugins

Claude Code version 2.1 or later is needed.

1. Open this repo in Claude Code (CLI or the VS Code extension).
2. When asked whether to trust the folder, accept.
3. Claude Code then offers to add the `ponytail` marketplace and install the plugins listed in `.claude/settings.json`. Accept both.

If you don't get the prompt, install them yourself from the repo root:

```sh
claude plugin install superpowers@claude-plugins-official --scope project
claude plugin marketplace add DietrichGebert/ponytail --scope project
claude plugin install ponytail@ponytail --scope project
```

Only install Ponytail from `DietrichGebert/ponytail` on GitHub. It never ships `.exe` or `.dll` files, so a copy that does is not genuine.

Then restart your Claude Code session so the skills load.

## 2. Check that it works

```sh
claude plugin list
```

You should see both `superpowers@claude-plugins-official` and `ponytail@ponytail` with `Scope: project` and `Status: ✔ enabled`.

Next, start a session and ask Claude to build something, like "let's add an endpoint to create a snippet". If the plugins are working, Claude asks about the design before it writes any code, and the session start text shows the current Ponytail level.

## 3. The workflow

The Superpowers skills run automatically. Every change goes through these steps:

| Step | Skill | What happens |
|---|---|---|
| Design | `brainstorming` | Claude asks what you want and why, then plays it back for you to correct. Small changes get agreed in chat. Bigger features get a written design doc. |
| Branch | `using-git-worktrees` | Claude creates a separate worktree on a new branch and checks that the tests pass before any changes. |
| Plan | `writing-plans` | Claude splits the approved design into tasks of 2–5 minutes each, with exact file paths, code, and how to check each one. |
| Build | `subagent-driven-development` or `executing-plans` | A subagent per task with a review after each, or all tasks in one session with a single review at the end. |
| Tests | `test-driven-development` | Red, green, refactor: write a failing test, watch it fail, write the least code that passes. Code written before its test gets deleted. |
| Review | `requesting-code-review` | Reviews the work against the plan between tasks. Critical issues block progress. |
| Finish | `finishing-a-development-branch` | Claude checks the tests pass, then asks whether to merge, open a PR, keep the branch, or discard it. |

Please don't skip these steps. Once you sign off on the design and plan, Claude does the rest.

## 4. Ponytail

Ponytail is always on and works inside every step above. Before writing code, it goes down this list and stops at the first option that works:

1. Does this need to exist?
2. Is it already in this codebase?
3. Does the standard library do it?
4. Does the platform do it natively?
5. Does a dependency we already have do it?
6. Can it be one line?
7. Only then: write the least code that works.

Every reply ends with what was skipped or not checked, and any risks.

| Command | What it does |
|---|---|
| `/ponytail [lite \| full \| ultra \| off]` | Set the level or turn it off. With no argument, it reports the current level. |
| `/ponytail-review` | Reviews the current diff and the code it touches: bugs, security, load, risky code without tests, slow paths, and what to cut. |
| `/ponytail-audit` | The same checks for the whole repo, most important first. |
| `/ponytail-debt` | Collects deliberate `shortcut:` comments into a list of things to come back to. |
| `/ponytail-help` | Quick reference. |

**The band** above the prompt shows each task's cost, tokens, agent time, how much code was reused, and test status. It needs Claude Code 2.1.290 or later in the terminal or desktop app. It doesn't show in the VS Code chat panel. Hide it with `/ponytail band off`.

**Data.** By default, Ponytail writes each task's numbers to `~/.config/ponytail/band/<project>.csv` on your machine, and nothing else leaves it. The optional `webhookUrl` setting (`/plugin configure ponytail@ponytail`) sends that data to a URL. Leave it empty unless the team agrees on a shared board.

## 5. Langfuse: docs MCP server and agent skill

[Langfuse](https://langfuse.com) is the observability tool for tracing, prompt management and evaluation of the test agent. The repo sets up two parts, both for this repo only:

| | What | Where |
|---|---|---|
| **Langfuse Docs MCP server** | Lets Claude search the Langfuse docs. Public, no login, transport `streamableHttp`. | `langfuse-docs` in [.mcp.json](../.mcp.json), at `https://langfuse.com/api/mcp` |
| **Langfuse Agent Skill** | Langfuse's playbook for instrumenting code, managing prompts and running evaluations. It reads and writes Langfuse data with `npx langfuse-cli`. | [skills/langfuse/](skills/langfuse/), with the version recorded in [skills-lock.json](../skills-lock.json) |

**MCP server.** The first time you open the repo, Claude Code asks whether to trust the servers in `.mcp.json`. Approve `langfuse-docs`, then type `/mcp` to check it shows as connected. If it's missing, add it from the repo root:

```sh
claude mcp add --transport http langfuse-docs https://langfuse.com/api/mcp --scope project
```

**Skill.** It loads with the repo. If `.claude/skills/langfuse/` is missing or out of date, restore or reinstall it from the repo root (Node.js is needed), then restart Claude Code:

```sh
npx skills experimental_install       # restore the version in skills-lock.json
# or reinstall the latest:
npx skills add langfuse/skills --skill langfuse --agent claude-code -y --copy
```

**Keys.** Searching the docs needs no keys. Reading or writing your own Langfuse traces, prompts or datasets does. Create an API key pair in the Langfuse project under Settings → API Keys, and put it in your shell or a git-ignored `.env`, never in chat:

```sh
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com   # EU cloud; https://us.cloud.langfuse.com for US, or your self-hosted URL
```

The skill runs with full agent permissions. Read [SKILL.md](skills/langfuse/SKILL.md) before you first use it.

**Local Langfuse.** This repo also runs its own Langfuse in Docker, at `http://localhost:3100`: `docker compose --profile langfuse up -d`. The test agent and both MCP servers send their traces there, and the evals and experiments use it. Use `LANGFUSE_BASE_URL=http://localhost:3100` with the keys from the root `.env`. Setup, reading traces and running evals: [test-agent/TESTING.md](../test-agent/TESTING.md#traces-and-evals).

## 6. Backend testing skill

[testing-fastapi-features](skills/testing-fastapi-features/SKILL.md) is a skill written for this repo. It runs automatically whenever Claude adds or changes a module, route, service, schema or feature in `backend/`. Each feature then gets **two test files**:

| | Unit | Integration |
|---|---|---|
| File | `backend/tests/unit/test_<feature>.py` | `backend/tests/integration/test_<feature>.py` |
| Tests | schemas, helpers, services and branches, called directly | the API over HTTP, end to end |
| Database | none, with fakes where needed | the real `snippet_test` Postgres |
| Run | `uv run pytest tests/unit` (no Docker) | `uv run pytest tests/integration` |

The first time it runs, Claude moves the current tests and their DB fixtures into `tests/integration/`. Without that move, unit tests would still need Postgres.

It works alongside `test-driven-development`: both files get failing tests before any code is written. A feature with only one of the two files isn't done. To call the skill yourself, type `/testing-fastapi-features`.

## 7. Optional settings

**Telemetry.** The optional visual companion in `brainstorming` loads the Prime Radiant logo from their website, which tells them which Superpowers version you use. To turn this off, set the environment variable in your shell:

```sh
export SUPERPOWERS_DISABLE_TELEMETRY=1
```

Superpowers also respects Claude Code's `DISABLE_TELEMETRY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`.

**Personal settings.** Put settings meant only for you in `.claude/settings.local.json`. Claude Code gitignores that file automatically. Only edit the shared `settings.json` for settings everyone on the team should get.

## 8. When something goes wrong

If a skill runs when it shouldn't, doesn't run when it should, or Claude stops following the plan, ask Claude:

> figure out what went wrong with superpowers in this session

That runs the `diagnosing-superpowers` skill, which reads the session transcript and shows what happened, citing the lines involved.

Plugin issues:
- Superpowers: https://github.com/obra/superpowers/issues
- Ponytail: https://github.com/DietrichGebert/ponytail/issues
