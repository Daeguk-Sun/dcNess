"""Read-only checker for impl design-reference node ids (#989)."""
from __future__ import annotations

import glob
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

__all__ = [
    "check_mockup_nodes",
    "collect_mockup_node_ids",
    "extract_design_reference_node_ids",
]

_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DESIGN_REF_HEADER_RE = re.compile(r"^##\s+디자인\s+참조\s*$")
_SECTION_HEADER_RE = re.compile(r"^##\s+")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_DENY_LITERALS = {
    "canvas.html",
    "data-node-id",
    "design",
    "docs",
    "node-id",
    "optional",
    "required",
}


class _NodeIdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.node_ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() == "data-node-id" and value:
                self.node_ids.add(value.strip())


def _is_excluded_mockup(path: Path) -> bool:
    parts = set(path.parts)
    return path.name == "canvas.html" or "drafts" in parts or "_lib" in parts


def _resolve_mockup_files(mockup_dir: str | Path) -> list[Path]:
    root = Path(mockup_dir)
    if root.is_file():
        return [root] if root.suffix.lower() == ".html" and not _is_excluded_mockup(root) else []
    if not root.is_dir():
        return []
    return [
        path
        for path in sorted(root.glob("*.html"))
        if path.is_file() and not _is_excluded_mockup(path)
    ]


def collect_mockup_node_ids(mockup_dir: str | Path) -> tuple[set[str], list[Path]]:
    """Collect data-node-id values from confirmed mockup HTML files."""
    node_ids: set[str] = set()
    files = _resolve_mockup_files(mockup_dir)
    for path in files:
        parser = _NodeIdParser()
        parser.feed(path.read_text(encoding="utf-8"))
        node_ids.update(parser.node_ids)
    return node_ids, files


def _resolve_impl_files(raw_paths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_paths:
        matches = glob.glob(raw, recursive=True) or [raw]
        for match in matches:
            path = Path(match)
            candidates: Iterable[Path]
            if path.is_dir():
                candidates = sorted(path.rglob("*.md"))
            elif path.is_file() and path.suffix.lower() == ".md":
                candidates = [path]
            else:
                candidates = []
            for candidate in candidates:
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(candidate)
    return files


def _design_reference_section(text: str) -> str:
    in_section = False
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _DESIGN_REF_HEADER_RE.match(stripped):
            in_section = True
            continue
        if in_section and _SECTION_HEADER_RE.match(stripped):
            break
        if in_section:
            lines.append(line)
    return "\n".join(lines)


def _clean_node_id_candidate(raw: str) -> str | None:
    candidate = raw.strip().strip("`'\"“”‘’,:;")
    if not candidate:
        return None
    if any(token in candidate for token in ("<", ">", "{", "}", "/", "\\")):
        return None
    if any(ch.isspace() for ch in candidate):
        return None
    lowered = candidate.lower()
    if lowered in _DENY_LITERALS or lowered.endswith((".html", ".md")):
        return None
    if not _NODE_ID_RE.match(candidate):
        return None
    return candidate


def _left_side_arrow_candidate(line: str) -> str | None:
    left = ""
    for sep in ("→", "->", "=>"):
        if sep in line:
            left = line.split(sep, 1)[0]
            break
    if not left:
        return None
    left = re.sub(r"^\s*[-*]\s*", "", left).strip()
    left = re.sub(r"^\d+\.\s*", "", left).strip()
    if ":" in left and "data-node-id" in left:
        left = left.rsplit(":", 1)[-1].strip()
    return _clean_node_id_candidate(left)


def extract_design_reference_node_ids(text: str) -> list[str]:
    """Extract cited node ids from an impl document's ``## 디자인 참조`` section."""
    section = _design_reference_section(text)
    if not section:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(candidate: str | None) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)

    for match in _BACKTICK_RE.finditer(section):
        add(_clean_node_id_candidate(match.group(1)))
    for line in section.splitlines():
        add(_left_side_arrow_candidate(line))
    return out


def check_mockup_nodes(raw_paths: Iterable[str], *, mockup_dir: str | Path) -> dict:
    """Check cited impl design-reference node ids against confirmed mockup files."""
    available_ids, mockup_files = collect_mockup_node_ids(mockup_dir)
    files_payload: list[dict] = []
    all_missing: set[str] = set()
    all_cited: set[str] = set()
    for impl_path in _resolve_impl_files(raw_paths):
        cited = extract_design_reference_node_ids(impl_path.read_text(encoding="utf-8"))
        existing = sorted(node_id for node_id in cited if node_id in available_ids)
        missing = sorted(node_id for node_id in cited if node_id not in available_ids)
        all_cited.update(cited)
        all_missing.update(missing)
        files_payload.append(
            {
                "path": str(impl_path),
                "cited_node_ids": sorted(cited),
                "existing_node_ids": existing,
                "missing_node_ids": missing,
            }
        )
    return {
        "ok": not all_missing,
        "mockup_dir": str(mockup_dir),
        "mockup_files": [str(path) for path in mockup_files],
        "available_node_ids": sorted(available_ids),
        "cited_node_ids": sorted(all_cited),
        "missing_node_ids": sorted(all_missing),
        "files": files_payload,
    }
