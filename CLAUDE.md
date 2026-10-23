# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

snippet-share is a lightweight pastebin-style service: users save text snippets, get a shareable link, and read the snippet back as plain text.

The planned design (FastAPI + React + PostgreSQL + Docker Compose) is in [.claude/PROJECT-IDEA.md](.claude/PROJECT-IDEA.md). It is an idea, not an approved design: start `brainstorming` from it and settle its open questions before planning.

## Workflow

This repo uses the Superpowers plugin, which is enabled in `.claude/settings.json`. Use its workflow for every change: `brainstorming` → `using-git-worktrees` → `writing-plans` → `subagent-driven-development` / `executing-plans` with `test-driven-development` → `requesting-code-review` → `finishing-a-development-branch`. Don't write implementation code before the design is approved and a failing test exists.

The Ponytail plugin is also enabled. Superpowers decides the process; Ponytail decides how little code each task needs. Where they disagree on testing, Superpowers' test-first rule wins.

Developer setup steps are in [.claude/CLAUDE-INITIAL-SETUP.md](.claude/CLAUDE-INITIAL-SETUP.md).

## Current state

The repository contains only `README.md`. No language, framework, build system, tests, or source layout has been chosen yet. Once code is added, update this file with:

- build, lint, and test commands, including how to run a single test
- the high-level architecture: storage, ID/link generation, and the HTTP routes for create, read, and raw text
