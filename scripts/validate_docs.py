from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ENTRYPOINTS = ("README.md", "AGENTS.md", "ARCHITECTURE.md")
ENTRYPOINT_LINE_BUDGETS = {
    "README.md": 220,
    "AGENTS.md": 140,
    "ARCHITECTURE.md": 140,
}
LANGUAGE_SWITCH_TARGETS = {
    "README.md": "README.zh.md",
    "README.zh.md": "README.md",
}
LANGUAGE_SWITCH_TOP_LINE_COUNT = 8
IGNORED_PARTS = {".git", ".venv", "artifacts"}
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
ISSUE_FIELD_RE = re.compile(
    r"^(?:- )?\*\*(Status|Assignee|Label|Parent map|Parent spec|Dependencies|What to build|Blocked by):\*\*\s*(.+)$",
    re.MULTILINE,
)
MARKDOWN_TARGET_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
FEATURE_TICKET_STATUSES = {"ready-for-agent", "in-progress", "blocked", "completed"}
FEATURE_TICKET_TITLE_RE = re.compile(r"^# (\d{2}) — \S.+$", re.MULTILINE)
WAYFINDER_MAP_STATUSES = {"open", "closed"}
WAYFINDER_DECISION_STATUSES = {"open", "closed"}
WAYFINDER_DIRECTORY_SUFFIX = "-wayfinding"
WAYFINDER_DECISIONS_DIRECTORY = "decisions"
WAYFINDER_DECISION_LABELS = {
    "`wayfinder:research`",
    "`wayfinder:prototype`",
    "`wayfinder:grilling`",
    "`wayfinder:task`",
}
WAYFINDER_MAP_SECTIONS = (
    "Destination",
    "Notes",
    "Decisions so far",
    "Not yet specified",
    "Out of scope",
)


@dataclass(frozen=True)
class ArtifactRegistry:
    context_mode: str
    issue_tracker_type: str | None
    issue_store: Path | None
    docs_areas: tuple[str, ...]
    adr_dirs: tuple[Path, ...]


def strip_fenced_blocks(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_fence and stripped.startswith(("```", "~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            continue
        if in_fence and stripped.startswith(fence_marker):
            in_fence = False
            fence_marker = ""
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def iter_markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts)
    )


def clean_link_target(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return unquote(target.split("#", 1)[0])


def resolve_link(source: Path, target: str) -> Path | None:
    if target.startswith(("http://", "https://", "mailto:", "tel:")):
        return None
    clean_target = clean_link_target(target)
    if not clean_target:
        return None
    return (source.parent / clean_target).resolve()


def contains_top_link(source: Path, target: Path, text: str) -> bool:
    top_text = "\n".join(text.splitlines()[:LANGUAGE_SWITCH_TOP_LINE_COUNT])
    return any(
        resolve_link(source, match.group(1)) == target.resolve()
        for match in LINK_RE.finditer(top_text)
    )


def is_wayfinder_map(text: str) -> bool:
    return dict(ISSUE_FIELD_RE.findall(text)).get("Label") == "`wayfinder:map`"


def is_wayfinder_map_path(map_path: Path) -> bool:
    return (
        map_path.name == "README.md"
        and map_path.parent.name.endswith(WAYFINDER_DIRECTORY_SUFFIX)
    )


def validate_wayfinder_map(
    map_path: Path,
    text: str,
    errors: list[str],
) -> None:
    fields = dict(ISSUE_FIELD_RE.findall(text))
    for field in ("Status", "Assignee", "Label"):
        if field not in fields:
            errors.append(
                f"{map_path.relative_to(ROOT)} missing wayfinder map field: {field}"
            )
    if fields.get("Status") not in WAYFINDER_MAP_STATUSES:
        errors.append(
            f"{map_path.relative_to(ROOT)} has unsupported wayfinder map status: "
            f"{fields.get('Status', '<missing>')}"
        )
    for section in WAYFINDER_MAP_SECTIONS:
        if not re.search(rf"^## {re.escape(section)}\s*$", text, re.MULTILINE):
            errors.append(
                f"{map_path.relative_to(ROOT)} missing wayfinder map section: {section}"
            )


def validate_wayfinder_decision(
    decision: Path,
    *,
    map_path: Path,
    decisions_dir: Path,
    errors: list[str],
) -> None:
    text = decision.read_text(encoding="utf-8")
    fields = dict(ISSUE_FIELD_RE.findall(text))
    for field in ("Status", "Assignee", "Label", "Parent map", "Blocked by"):
        if field not in fields:
            errors.append(
                f"{decision.relative_to(ROOT)} missing wayfinder decision field: {field}"
            )
    if fields.get("Status") not in WAYFINDER_DECISION_STATUSES:
        errors.append(
            f"{decision.relative_to(ROOT)} has unsupported wayfinder decision status: "
            f"{fields.get('Status', '<missing>')}"
        )
    if fields.get("Label") not in WAYFINDER_DECISION_LABELS:
        errors.append(
            f"{decision.relative_to(ROOT)} has unsupported wayfinder decision label: "
            f"{fields.get('Label', '<missing>')}"
        )
    if not re.search(r"^# \S.+$", text, re.MULTILINE):
        errors.append(f"{decision.relative_to(ROOT)} must have a named decision title")
    if not re.search(r"^## Question\s*$", text, re.MULTILINE):
        errors.append(f"{decision.relative_to(ROOT)} must declare one Question section")
    if fields.get("Status") == "closed" and not re.search(
        r"^## Resolution comment\s*$",
        text,
        re.MULTILINE,
    ):
        errors.append(
            f"{decision.relative_to(ROOT)} closed wayfinder decision must have a Resolution comment"
        )

    parent = fields.get("Parent map", "")
    parent_match = MARKDOWN_TARGET_RE.search(parent)
    parent_target = (
        resolve_link(decision, parent_match.group(1)) if parent_match else None
    )
    if parent_target != map_path.resolve():
        errors.append(
            f"{decision.relative_to(ROOT)} parent map must link to "
            f"{map_path.relative_to(ROOT)}"
        )

    decision_number = decision.name[:2]
    blocked_by = fields.get("Blocked by", "")
    for blocker_match in MARKDOWN_TARGET_RE.finditer(blocked_by):
        blocker = resolve_link(decision, blocker_match.group(1))
        if (
            blocker is None
            or blocker.parent != decisions_dir.resolve()
            or not blocker.is_file()
        ):
            errors.append(
                f"{decision.relative_to(ROOT)} blockers must be decisions in the same map"
            )
            continue
        blocker_number = blocker.name[:2]
        if not blocker_number.isdigit() or blocker_number >= decision_number:
            errors.append(
                f"{decision.relative_to(ROOT)} blocker must have a lower decision number: "
                f"{blocker.name}"
            )


def discover_artifacts(errors: list[str]) -> ArtifactRegistry:
    context = ROOT / "CONTEXT.md"
    context_map = ROOT / "CONTEXT-MAP.md"
    if context.exists() and context_map.exists():
        errors.append("CONTEXT.md and CONTEXT-MAP.md cannot both be authoritative")
        context_mode = "invalid"
    elif context_map.exists():
        context_mode = "multi"
    elif context.exists():
        context_mode = "single"
    else:
        context_mode = "none"

    tracker_config = ROOT / "docs/agents/issue-tracker.md"
    tracker_type: str | None = None
    issue_store: Path | None = None
    if tracker_config.exists():
        tracker_text = tracker_config.read_text(encoding="utf-8")
        if "**Type:** Local Markdown" in tracker_text:
            tracker_type = "Local Markdown"
            issue_store = ROOT / ".scratch"
        else:
            type_match = re.search(r"\*\*Type:\*\*\s*(.+)", tracker_text)
            tracker_type = type_match.group(1).strip() if type_match else "unknown"

    docs_root = ROOT / "docs"
    docs_areas = tuple(
        path.name
        for path in sorted(docs_root.iterdir())
        if path.is_dir()
        and path.name != "exec-plans"
        and any(path.rglob("*.md"))
    ) if docs_root.is_dir() else ()

    adr_dirs = tuple(
        path for path in ROOT.rglob("adr")
        if path.is_dir()
        and "docs" in path.parts
        and not any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts)
    )
    return ArtifactRegistry(context_mode, tracker_type, issue_store, docs_areas, adr_dirs)


def validate_entrypoints(errors: list[str]) -> None:
    for rel_path in REQUIRED_ENTRYPOINTS:
        path = ROOT / rel_path
        if not path.is_file():
            errors.append(f"Missing required entrypoint: {rel_path}")
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        budget = ENTRYPOINT_LINE_BUDGETS[rel_path]
        if line_count > budget:
            errors.append(f"{rel_path} is too long: {line_count} lines (budget {budget})")

    if (ROOT / "docs").is_dir() and not (ROOT / "docs/README.md").is_file():
        errors.append("docs/README.md is required when docs/ contains canonical docs")

    required_links = {
        "README.md": ("AGENTS.md", "ARCHITECTURE.md", "docs/README.md"),
        "AGENTS.md": ("README.md", "ARCHITECTURE.md", "docs/README.md"),
        "ARCHITECTURE.md": ("docs/DESIGN.md", "docs/design-docs/agent-data-synthesis-framework.md"),
    }
    for rel_path, targets in required_links.items():
        path = ROOT / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for target in targets:
            if target not in text:
                errors.append(f"{rel_path} must link to {target}")


def validate_language_switches(errors: list[str]) -> None:
    for source_rel, target_rel in LANGUAGE_SWITCH_TARGETS.items():
        source = ROOT / source_rel
        target = ROOT / target_rel
        if not source.is_file():
            errors.append(f"Missing localized README: {source_rel}")
            continue
        if not target.is_file():
            errors.append(f"Missing localized README: {target_rel}")
            continue
        text = source.read_text(encoding="utf-8")
        if not contains_top_link(source, target, text):
            errors.append(
                f"{source_rel} must link to {target_rel} within its first "
                f"{LANGUAGE_SWITCH_TOP_LINE_COUNT} lines"
            )


def validate_links(errors: list[str]) -> None:
    for md_file in iter_markdown_files():
        text = strip_fenced_blocks(md_file.read_text(encoding="utf-8"))
        for match in LINK_RE.finditer(text):
            resolved = resolve_link(md_file, match.group(1))
            if resolved is None:
                continue
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"Internal link escapes repository in {md_file.relative_to(ROOT)}: "
                    f"{match.group(1)}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"Broken link in {md_file.relative_to(ROOT)}: {match.group(1)}"
                )


def validate_context(registry: ArtifactRegistry, errors: list[str]) -> None:
    if registry.context_mode == "single":
        context = ROOT / "CONTEXT.md"
        text = context.read_text(encoding="utf-8")
        for owner in ("README.md", "AGENTS.md", "ARCHITECTURE.md", "docs/README.md"):
            owner_path = ROOT / owner
            if owner_path.exists() and "CONTEXT.md" not in owner_path.read_text(encoding="utf-8"):
                errors.append(f"{owner} must link to the active CONTEXT.md glossary")
        forbidden_headings = ("## Implementation", "## Architecture", "## Status", "## Tasks")
        for heading in forbidden_headings:
            if heading in text:
                errors.append(f"CONTEXT.md is glossary-only and cannot contain {heading}")

    if registry.context_mode == "multi":
        context_map = ROOT / "CONTEXT-MAP.md"
        text = strip_fenced_blocks(context_map.read_text(encoding="utf-8"))
        context_targets = []
        for match in LINK_RE.finditer(text):
            resolved = resolve_link(context_map, match.group(1))
            if resolved is not None and resolved.name == "CONTEXT.md":
                context_targets.append(resolved)
        if not context_targets:
            errors.append("CONTEXT-MAP.md must link to at least one context glossary")
        for target in context_targets:
            if not target.is_file():
                errors.append(f"CONTEXT-MAP.md references missing glossary: {target}")


def validate_docs_index(registry: ArtifactRegistry, errors: list[str]) -> None:
    index = ROOT / "docs/README.md"
    if not index.exists():
        return
    text = index.read_text(encoding="utf-8")
    for heading in ("Core Docs", "Deep Design", "Product Specs", "References"):
        if heading not in text:
            errors.append(f"docs/README.md missing section: {heading}")
    for area in registry.docs_areas:
        if f"{area}/" not in text:
            errors.append(f"Active docs area is not indexed in docs/README.md: docs/{area}/")


def validate_issue_tracker(registry: ArtifactRegistry, errors: list[str]) -> None:
    agents_map = ROOT / "AGENTS.md"
    docs_index = ROOT / "docs/README.md"
    if (ROOT / "docs/agents").is_dir():
        for owner in (agents_map, docs_index):
            if owner.exists() and "agents/issue-tracker.md" not in owner.read_text(encoding="utf-8"):
                errors.append(
                    f"{owner.relative_to(ROOT)} must link to docs/agents/issue-tracker.md"
                )

    scratch = ROOT / ".scratch"
    if registry.issue_tracker_type == "Local Markdown":
        if registry.issue_store != scratch or not scratch.is_dir():
            errors.append("Local Markdown tracker must use an existing .scratch/ store")
            return
        if not (scratch / "README.md").is_file():
            errors.append("Local Markdown tracker requires .scratch/README.md")
        for issue in sorted(scratch.glob("ISSUE-*.md")):
            text = issue.read_text(encoding="utf-8")
            fields = dict(ISSUE_FIELD_RE.findall(text))
            for field in ("Status", "Assignee", "Parent spec", "Dependencies"):
                if field not in fields:
                    errors.append(f"{issue.relative_to(ROOT)} missing issue field: {field}")
            parent = fields.get("Parent spec", "")
            target_match = MARKDOWN_TARGET_RE.search(parent)
            if not target_match:
                errors.append(f"{issue.relative_to(ROOT)} must link to one parent spec")
                continue
            target = resolve_link(issue, target_match.group(1))
            specs_root = (ROOT / "docs/product-specs").resolve()
            if target is None or not target.is_file() or target.parent != specs_root:
                errors.append(
                    f"{issue.relative_to(ROOT)} parent spec must be a file in docs/product-specs/"
                )

        scratch_index_text = (scratch / "README.md").read_text(encoding="utf-8")

        wayfinder_map_dirs: set[Path] = set()
        for map_index in sorted(scratch.glob("*/README.md")):
            map_text = map_index.read_text(encoding="utf-8")
            if not is_wayfinder_map(map_text):
                continue

            map_dir = map_index.parent
            wayfinder_map_dirs.add(map_dir.resolve())
            if not is_wayfinder_map_path(map_index):
                errors.append(
                    f"Wayfinder map directory must end with "
                    f"{WAYFINDER_DIRECTORY_SUFFIX}: {map_dir.relative_to(ROOT)}"
                )
            if map_dir.name + "/README.md" not in scratch_index_text:
                errors.append(
                    f".scratch/README.md must link wayfinder map: "
                    f"{map_index.relative_to(ROOT)}"
                )

            validate_wayfinder_map(map_index, map_text, errors)
            decisions_dir = map_dir / WAYFINDER_DECISIONS_DIRECTORY
            if not decisions_dir.is_dir():
                errors.append(
                    f"Wayfinder map requires a decisions directory: "
                    f"{decisions_dir.relative_to(ROOT)}"
                )
                continue
            for decision in sorted(decisions_dir.glob("*.md")):
                if not re.fullmatch(r"\d{2}-[a-z0-9-]+\.md", decision.name):
                    errors.append(
                        f"Wayfinder decision filename must use NN-kebab-case.md: "
                        f"{decision.relative_to(ROOT)}"
                    )
                validate_wayfinder_decision(
                    decision,
                    map_path=map_index,
                    decisions_dir=decisions_dir,
                    errors=errors,
                )

        for decisions_dir in sorted(scratch.glob("*/decisions")):
            if decisions_dir.parent.resolve() not in wayfinder_map_dirs:
                errors.append(
                    f"Decision directory requires a wayfinder map index: "
                    f"{decisions_dir.relative_to(ROOT)}"
                )

        feature_issue_dirs = sorted(scratch.glob("*/issues"))
        for issues_dir in feature_issue_dirs:
            feature_dir = issues_dir.parent
            feature_index = feature_dir / "README.md"
            if not feature_index.is_file():
                errors.append(
                    f"Feature ticket directory requires an index: {feature_index.relative_to(ROOT)}"
                )
                continue
            if feature_dir.name + "/README.md" not in scratch_index_text:
                errors.append(
                    f".scratch/README.md must link feature tracker: {feature_index.relative_to(ROOT)}"
                )

            feature_text = feature_index.read_text(encoding="utf-8")
            if is_wayfinder_map(feature_text):
                errors.append(
                    f"Wayfinder decisions must use a {WAYFINDER_DIRECTORY_SUFFIX}/"
                    f"{WAYFINDER_DECISIONS_DIRECTORY}/ layout, not "
                    f"{issues_dir.relative_to(ROOT)}"
                )
                continue
            if feature_dir.name.endswith(WAYFINDER_DIRECTORY_SUFFIX):
                errors.append(
                    f"Implementation feature directory must not use the wayfinder suffix: "
                    f"{feature_dir.relative_to(ROOT)}"
                )
                continue

            for issue in sorted(issues_dir.glob("*.md")):
                if not re.fullmatch(r"\d{2}-[a-z0-9-]+\.md", issue.name):
                    errors.append(
                        f"Feature ticket filename must use NN-kebab-case.md: {issue.relative_to(ROOT)}"
                    )
                if f"issues/{issue.name}" not in feature_text:
                    errors.append(
                        f"Feature index must link ticket: {issue.relative_to(ROOT)}"
                    )

                text = issue.read_text(encoding="utf-8")
                title_match = FEATURE_TICKET_TITLE_RE.search(text)
                issue_number = issue.name[:2]
                if not title_match or title_match.group(1) != issue_number:
                    errors.append(
                        f"{issue.relative_to(ROOT)} title number must match filename: "
                        f"{issue_number}"
                    )
                fields = dict(ISSUE_FIELD_RE.findall(text))
                for field in ("What to build", "Blocked by", "Status", "Assignee", "Parent spec"):
                    if field not in fields:
                        errors.append(
                            f"{issue.relative_to(ROOT)} missing feature ticket field: {field}"
                        )
                if fields.get("Status") not in FEATURE_TICKET_STATUSES:
                    errors.append(
                        f"{issue.relative_to(ROOT)} has unsupported feature ticket status: "
                        f"{fields.get('Status', '<missing>')}"
                    )
                if not re.search(r"^## Acceptance criteria\s*$", text, re.MULTILINE):
                    errors.append(
                        f"{issue.relative_to(ROOT)} must declare acceptance criteria"
                    )
                if not re.search(r"^- \[[ xX]\] ", text, re.MULTILINE):
                    errors.append(
                        f"{issue.relative_to(ROOT)} must contain acceptance checkboxes"
                    )

                blocked_by = fields.get("Blocked by", "")
                for blocker_match in MARKDOWN_TARGET_RE.finditer(blocked_by):
                    blocker = resolve_link(issue, blocker_match.group(1))
                    if blocker is None or blocker.parent != issues_dir.resolve():
                        errors.append(
                            f"{issue.relative_to(ROOT)} blockers must be tickets in the same feature"
                        )
                        continue
                    blocker_number = blocker.name[:2]
                    if not blocker_number.isdigit() or blocker_number >= issue_number:
                        errors.append(
                            f"{issue.relative_to(ROOT)} blocker must have a lower ticket number: "
                            f"{blocker.name}"
                        )

                parent = fields.get("Parent spec", "")
                target_match = MARKDOWN_TARGET_RE.search(parent)
                if not target_match:
                    errors.append(f"{issue.relative_to(ROOT)} must link to one parent spec")
                    continue
                target = resolve_link(issue, target_match.group(1))
                specs_root = (ROOT / "docs/product-specs").resolve()
                if target is None or not target.is_file() or target.parent != specs_root:
                    errors.append(
                        f"{issue.relative_to(ROOT)} parent spec must be a file in docs/product-specs/"
                    )
    elif scratch.exists():
        errors.append(".scratch/ may be an issue store only when Local Markdown is configured")


def validate_work_boundaries(errors: list[str]) -> None:
    for directory in (ROOT / "docs/product-specs", ROOT / "docs/design-docs"):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.md"):
            text = strip_fenced_blocks(path.read_text(encoding="utf-8"))
            if re.search(r"^- \[[ xX]\]", text, re.MULTILINE):
                errors.append(
                    f"Live task checklist belongs in the issue tracker, not {path.relative_to(ROOT)}"
                )

    plans = ROOT / "docs/PLANS.md"
    if plans.exists():
        text = plans.read_text(encoding="utf-8")
        for marker in ("historical", "not a parallel work tracker", "No new execution-plan"):
            if marker.lower() not in text.lower():
                errors.append(f"docs/PLANS.md must declare legacy boundary: {marker}")

    active_dir = ROOT / "docs/exec-plans/active"
    if active_dir.is_dir():
        unexpected = [path for path in active_dir.iterdir() if path.name != "README.md"]
        if unexpected:
            errors.append("Legacy docs/exec-plans/active/ must not receive new plan files")

    deferred_dir = ROOT / "docs/exec-plans/deferred"
    if deferred_dir.is_dir():
        for path in deferred_dir.glob("*.md"):
            if path.name == "README.md":
                continue
            text = path.read_text(encoding="utf-8")
            if "Legacy record" not in text or ".scratch/ISSUE-" not in text:
                errors.append(
                    f"Archived deferred record must link to canonical issue: {path.relative_to(ROOT)}"
                )


def validate_adrs(registry: ArtifactRegistry, errors: list[str]) -> None:
    if not registry.adr_dirs:
        return
    architecture_text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    docs_index_text = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    for adr_dir in registry.adr_dirs:
        rel_dir = adr_dir.relative_to(ROOT).as_posix()
        if rel_dir == "docs/adr" and "docs/adr" not in architecture_text + docs_index_text:
            errors.append("System-wide docs/adr/ must be reachable from an entrypoint")
        for adr in adr_dir.glob("*.md"):
            if adr.name == "README.md":
                continue
            text = adr.read_text(encoding="utf-8")
            if not re.match(r"\d{4}-[a-z0-9-]+\.md$", adr.name):
                errors.append(f"ADR filename must use NNNN-kebab-case.md: {adr.relative_to(ROOT)}")
            if not re.search(r"^## Status\s*$", text, re.MULTILINE):
                errors.append(f"ADR must declare explicit status: {adr.relative_to(ROOT)}")


def main() -> int:
    errors: list[str] = []
    registry = discover_artifacts(errors)
    validate_entrypoints(errors)
    validate_language_switches(errors)
    validate_links(errors)
    validate_context(registry, errors)
    validate_docs_index(registry, errors)
    validate_issue_tracker(registry, errors)
    validate_work_boundaries(errors)
    validate_adrs(registry, errors)

    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Documentation validation passed "
        f"(context={registry.context_mode}, "
        f"issue_tracker={registry.issue_tracker_type or 'none'}, "
        f"docs_areas={len(registry.docs_areas)}, adr_scopes={len(registry.adr_dirs)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
