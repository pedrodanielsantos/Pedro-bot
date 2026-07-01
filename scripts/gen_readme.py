"""Regenerate the command reference table in README.md from the cogs.

This is a dev tool, not part of the running bot. It statically parses every
cog for its slash commands (name + description) and rewrites the block between
the ``<!-- COMMANDS:START -->`` / ``<!-- COMMANDS:END -->`` markers in the
README. Command categories and their order are read straight from
``cogs/commands/help.py`` so the README, and the in-Discord /help, stay in sync
from a single source of truth.

Run it from anywhere:

    py -3.13 scripts/gen_readme.py

Exit codes:
    0  README was already up to date (no changes written)
    10 README was regenerated (changes written)
    1  something went wrong
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COGS_DIR = ROOT / "cogs"
HELP_FILE = COGS_DIR / "commands" / "help.py"
README = ROOT / "README.md"

START_MARKER = "<!-- COMMANDS:START -->"
END_MARKER = "<!-- COMMANDS:END -->"

DEFAULT_DESCRIPTION = "No description provided."


def _literal_assignments(source: str, names: set[str]) -> dict[str, object]:
    """Pull top-level ``NAME = <literal>`` assignments out of a module source."""
    tree = ast.parse(source)
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                found[target.id] = ast.literal_eval(node.value)
    return found


def load_help_config() -> tuple[dict[str, str], list[str], str]:
    """Read the category map / order / default from help.py (no import needed)."""
    cfg = _literal_assignments(
        HELP_FILE.read_text(encoding="utf-8"),
        {"COMMAND_CATEGORIES", "CATEGORY_ORDER", "DEFAULT_CATEGORY"},
    )
    return (
        cfg.get("COMMAND_CATEGORIES", {}),
        cfg.get("CATEGORY_ORDER", []),
        cfg.get("DEFAULT_CATEGORY", "Other"),
    )


def _is_slash_decorator(dec: ast.expr) -> bool:
    """True for @app_commands.command(...) and @commands.hybrid_command(...)."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return False
    if dec.func.attr == "hybrid_command":
        return True
    # Plain "command" must be app_commands.command, not commands.command
    # (the latter are prefix-only owner tools we intentionally skip).
    return (
        dec.func.attr == "command"
        and isinstance(dec.func.value, ast.Name)
        and dec.func.value.id == "app_commands"
    )


def _decorator_kwargs(dec: ast.Call) -> dict[str, str]:
    out: dict[str, str] = {}
    for kw in dec.keywords:
        if kw.arg in ("name", "description") and isinstance(kw.value, ast.Constant):
            out[kw.arg] = kw.value.value
    return out


def _group_name(cls: ast.ClassDef) -> str | None:
    for kw in cls.keywords:
        if kw.arg == "group_name" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def collect_commands() -> list[tuple[str, str]]:
    """Return (qualified_name, description) for every slash command in cogs/."""
    commands: list[tuple[str, str]] = []
    for path in sorted(COGS_DIR.rglob("*.py")):
        if path.name.startswith("__"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            group = _group_name(cls)
            for item in cls.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in item.decorator_list:
                    if not _is_slash_decorator(dec):
                        continue
                    kwargs = _decorator_kwargs(dec)
                    name = kwargs.get("name")
                    if not name:
                        continue
                    qualified = f"{group} {name}" if group else name
                    desc = kwargs.get("description") or DEFAULT_DESCRIPTION
                    commands.append((qualified, desc))
                    break
    return commands


def category_for(qualified: str, categories: dict[str, str], default: str) -> str:
    if qualified in categories:
        return categories[qualified]
    root = qualified.split(" ", 1)[0]
    return categories.get(root, default)


def render_table() -> str:
    categories, order, default = load_help_config()
    commands = collect_commands()

    buckets: dict[str, list[tuple[str, str]]] = {}
    for qualified, desc in commands:
        cat = category_for(qualified, categories, default)
        buckets.setdefault(cat, []).append((qualified, desc))

    ordered = [c for c in order if c in buckets]
    ordered += [c for c in buckets if c not in order]

    lines: list[str] = []
    for cat in ordered:
        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| Command | Description |")
        lines.append("| --- | --- |")
        for qualified, desc in sorted(buckets[cat]):
            lines.append(f"| `/{qualified}` | {desc} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if not README.exists():
        print(f"[gen_readme] README not found at {README}", file=sys.stderr)
        return 1

    text = README.read_text(encoding="utf-8")
    if START_MARKER not in text or END_MARKER not in text:
        print(
            f"[gen_readme] markers not found; add {START_MARKER} / {END_MARKER} "
            "around the command section in README.md",
            file=sys.stderr,
        )
        return 1

    before, rest = text.split(START_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)

    table = render_table()
    new_text = f"{before}{START_MARKER}\n\n{table}\n{END_MARKER}{after}"

    if new_text == text:
        print("[gen_readme] README already up to date.")
        return 0

    README.write_text(new_text, encoding="utf-8")
    print("[gen_readme] README command table regenerated.")
    return 10


if __name__ == "__main__":
    sys.exit(main())
