---
name: ask-human
description: Ask the human user a question and return their reply. Tool ask_human(question str, context str) -> str. Use when you need user input (preferences, confirmations, missing parameters). Scripts ask.py (usage: python ask.py "Question" or echo "Question" | python ask.py).
skill_type: operator
---

# Ask Human Skill

Allows the agent to pause and ask the human a question, then continue with the user's reply.

## Tool

- **ask_human(question: str, context: str) -> str** — Ask the user a question with optional context; returns the user's input.

## Scripts

- **ask.py** — Prints the question (and optional context) to stdout, reads one line via `input()`, and prints that line as the result. Usage: `python ask.py "Your question"` or pass question as first argument; optional second argument is context.

## When to use

- When a decision requires human preference or confirmation.
- When a parameter is missing and must be supplied by the user.
- When the agent needs explicit approval before a destructive or costly action.
