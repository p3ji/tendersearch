"""Validate frontmatter on slash commands and agent skills.

These markdown files are the product surface — a command with broken
frontmatter silently fails to register, which looks like "the command
doesn't exist" rather than like an error. Checked in CI so drift cannot
accumulate unnoticed.

Rules:
  .claude/commands/*.md        need `description`
                               need `argument-hint` if they use $1
  **/SKILL.md                  need `name` and `description`

Usage:
    python tools/lint_skills.py
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def parse_frontmatter(path: pathlib.Path) -> dict[str, str] | None:
    """Return the frontmatter keys, or None if the block is absent/malformed."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def check(path: pathlib.Path, required: tuple[str, ...]) -> list[str]:
    rel = path.relative_to(REPO).as_posix()
    fields = parse_frontmatter(path)
    if fields is None:
        return [f"{rel}: missing or malformed YAML frontmatter"]

    problems = [f"{rel}: frontmatter missing '{k}'" for k in required if not fields.get(k)]

    # A command that interpolates $1 takes an argument, so it must hint at it.
    if path.match(".claude/commands/*.md"):
        body = path.read_text(encoding="utf-8")
        if "$1" in body and not fields.get("argument-hint"):
            problems.append(f"{rel}: uses $1 but has no 'argument-hint'")
    return problems


def main() -> int:
    problems: list[str] = []
    checked = 0

    commands = sorted((REPO / ".claude" / "commands").glob("*.md"))
    skills = sorted(REPO.glob(".claude/skills/**/SKILL.md")) + sorted(
        REPO.glob(".agents/skills/**/SKILL.md")
    )

    if not commands:
        problems.append(".claude/commands/: no command files found")
    if not skills:
        problems.append("no SKILL.md files found")

    for path in commands:
        problems += check(path, ("description",))
        checked += 1
    for path in skills:
        problems += check(path, ("name", "description"))
        checked += 1

    if problems:
        print(f"FAIL - {len(problems)} problem(s) across {checked} file(s):\n")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(f"OK - {checked} command and skill file(s) have valid frontmatter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
