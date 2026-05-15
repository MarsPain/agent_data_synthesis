from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "docs/README.md",
    "docs/DESIGN.md",
    "docs/BACKEND.md",
    "docs/DATA.md",
    "docs/SECURITY.md",
    "docs/PLANS.md",
    "docs/design-docs/architecture-explainers.md",
    "docs/design-docs/agent-data-synthesis-framework.md",
    "docs/references/agent-data-synthesis-pdf-analysis.md",
]

REQUIRED_DIRS = [
    "docs/design-docs",
    "docs/exec-plans/active",
    "docs/exec-plans/completed",
    "docs/exec-plans/tech-debt",
    "docs/generated",
    "docs/product-specs",
    "docs/references",
]

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def strip_fenced_blocks(text: str) -> str:
    lines = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def iter_markdown_files() -> list[Path]:
    ignored_parts = {".venv"}
    return [
        path
        for path in ROOT.rglob("*.md")
        if not any(part in ignored_parts for part in path.relative_to(ROOT).parts)
    ]


def resolve_link(source: Path, target: str) -> Path | None:
    if target.startswith(("http://", "https://", "mailto:")):
        return None
    clean_target = target.split("#", 1)[0]
    if not clean_target:
        return None
    return (source.parent / clean_target).resolve()


def validate_required_paths(errors: list[str]) -> None:
    for rel_path in REQUIRED_FILES:
        if not (ROOT / rel_path).is_file():
            errors.append(f"Missing required file: {rel_path}")
    for rel_path in REQUIRED_DIRS:
        if not (ROOT / rel_path).is_dir():
            errors.append(f"Missing required directory: {rel_path}")


def validate_links(errors: list[str]) -> None:
    for md_file in iter_markdown_files():
        text = strip_fenced_blocks(md_file.read_text(encoding="utf-8"))
        for match in LINK_RE.finditer(text):
            resolved = resolve_link(md_file, match.group(1))
            if resolved is None:
                continue
            if not resolved.exists():
                rel_source = md_file.relative_to(ROOT)
                errors.append(f"Broken link in {rel_source}: {match.group(1)}")


def validate_agents_map(errors: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    if not agents.exists():
        return
    text = agents.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > 140:
        errors.append(f"AGENTS.md is too long: {line_count} lines")
    for required_link in ["docs/README.md", "docs/DESIGN.md", "docs/PLANS.md"]:
        if required_link not in text:
            errors.append(f"AGENTS.md must link to {required_link}")


def validate_architecture_map(errors: list[str]) -> None:
    architecture = ROOT / "ARCHITECTURE.md"
    if not architecture.exists():
        return
    text = architecture.read_text(encoding="utf-8")
    for required_link in [
        "docs/DESIGN.md",
        "docs/design-docs/agent-data-synthesis-framework.md",
    ]:
        if required_link not in text:
            errors.append(f"ARCHITECTURE.md must link to {required_link}")


def validate_docs_index(errors: list[str]) -> None:
    docs_index = ROOT / "docs/README.md"
    if not docs_index.exists():
        return
    text = docs_index.read_text(encoding="utf-8")
    for required_section in ["Core Docs", "Deep Design", "References", "Execution Plans"]:
        if required_section not in text:
            errors.append(f"docs/README.md missing section: {required_section}")


def main() -> int:
    errors: list[str] = []
    validate_required_paths(errors)
    validate_links(errors)
    validate_agents_map(errors)
    validate_architecture_map(errors)
    validate_docs_index(errors)

    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Documentation validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
