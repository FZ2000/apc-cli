"""Non-destructive memory-file writing.

Uses HTML-comment markers to delimit the APC-managed section inside an
existing markdown file (e.g. CLAUDE.md, USER.md).  User content outside
the markers is never touched.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

BEGIN_MARKER = "<!-- BEGIN APC SYNCED CONTEXT - DO NOT EDIT THIS SECTION -->"
END_MARKER = "<!-- END APC SYNCED CONTEXT -->"


def build_memory_section(
    entries: List[Dict],
    category_headers: Dict[str, str],
    title: str = "AI Context — Synced by apc",
) -> str:
    """Build the markdown that goes between the APC markers.

    Returns the *inner* content (without the markers themselves).
    """
    by_category: Dict[str, List[str]] = {}
    for entry in entries:
        cat = entry.get("category", "preference")
        content = entry.get("content", "")
        if content:
            by_category.setdefault(cat, []).append(content)

    lines = [f"# {title}", ""]
    for category, header in category_headers.items():
        items = by_category.get(category, [])
        if items:
            lines.append(f"## {header}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    return "\n".join(lines)


def read_and_split(file_path: Path) -> Tuple[str, Optional[str], str]:
    """Split an existing file into (before, apc_section, after).

    *before*  — everything before BEGIN_MARKER (or full file if no markers)
    *apc_section* — content between markers (None if no markers found)
    *after*   — everything after END_MARKER
    """
    if not file_path.exists():
        return ("", None, "")

    text = file_path.read_text(encoding="utf-8")

    begin_idx = text.find(BEGIN_MARKER)
    if begin_idx == -1:
        return (text, None, "")

    end_idx = text.find(END_MARKER, begin_idx)
    if end_idx == -1:
        # Malformed: BEGIN without END — treat everything after BEGIN as the section
        return (text[:begin_idx], text[begin_idx:], "")

    before = text[:begin_idx]
    section = text[begin_idx : end_idx + len(END_MARKER)]
    after = text[end_idx + len(END_MARKER) :]

    return (before, section, after)


def _wrap_section(inner: str) -> str:
    """Wrap inner content with BEGIN/END markers."""
    return f"{BEGIN_MARKER}\n{inner}\n{END_MARKER}\n"


def write_memory_file(
    file_path: Path,
    entries: List[Dict],
    category_headers: Dict[str, str],
    title: str = "AI Context — Synced by apc",
) -> str:
    """Replace only the APC section in *file_path*, preserving user content.

    Returns the inner section content (for checksum recording).

    Behaviour:
    - File doesn't exist → create with just the APC section
    - File exists, no APC section → append APC section at end
    - File exists with APC section → replace only that section
    """
    inner = build_memory_section(entries, category_headers, title=title)
    wrapped = _wrap_section(inner)

    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(wrapped, encoding="utf-8")
        return inner

    before, existing_section, after = read_and_split(file_path)

    if existing_section is None:
        # No existing section — append
        # Ensure there's a blank line before the section
        separator = "\n" if before and not before.endswith("\n\n") else ""
        new_content = before + separator + wrapped
    else:
        # Replace existing section
        new_content = before + wrapped + after

    file_path.write_text(new_content, encoding="utf-8")
    return inner


def remove_memory_section(file_path: Path) -> bool:
    """Strip the APC section from *file_path*, keeping user content.

    Returns True if a section was found and removed.
    """
    if not file_path.exists():
        return False

    before, existing_section, after = read_and_split(file_path)

    if existing_section is None:
        return False

    # Reassemble without the APC section
    new_content = before + after

    # Clean up trailing whitespace / excessive blank lines
    new_content = new_content.rstrip("\n") + "\n" if new_content.strip() else ""

    file_path.write_text(new_content, encoding="utf-8")
    return True
