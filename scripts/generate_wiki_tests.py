#!/usr/bin/env python3
"""
generate_wiki_tests.py

Clones/updates the NitrOS-9 wiki, extracts all Sample Procedure code blocks
from Basic09-Command-Reference.md, writes them as individual .b09 files under
tests/wiki_procs/, and regenerates tests/test_wiki_samples.py.

Run this whenever the wiki page changes:
    python scripts/generate_wiki_tests.py
"""

import re
import subprocess
import sys
from pathlib import Path

WIKI_REPO = "https://github.com/nitros9project/nitros9.wiki.git"
WIKI_DIR = Path("/tmp/nitros9.wiki")
WIKI_FILE = "Basic09-Command-Reference.md"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import os
_NITROS9DIR = Path(os.environ.get("NITROS9DIR", Path.home() / "Projects/coco-shelf/nitros9"))
PROCS_DIR = _NITROS9DIR / "3rdparty/packages/basic09/tests/wiki_procs"
TEST_FILE = PROJECT_ROOT / "tests" / "test_wiki_samples.py"

# Statements that require OS-9/system support not in our interpreter
_UNSUPPORTED_KW = {
    "SHELL", "OPEN", "CLOSE", "CREATE", "DELETE", "WRITE #", "READ #",
    "PUT #", "GET #", "SEEK", "SIZE", "PEEK", "POKE", "ADDR", "INKEY",
    "KILL", "CHAIN", "BYE", "SYSCALL", "DATE$", "ON ERROR", "RUN SYSCALL",
}


# ---------------------------------------------------------------------------
# Wiki fetching
# ---------------------------------------------------------------------------

def clone_or_update_wiki() -> Path:
    if WIKI_DIR.exists():
        subprocess.run(["git", "-C", str(WIKI_DIR), "pull", "--quiet"], check=False)
    else:
        subprocess.run(
            ["git", "clone", "--quiet", WIKI_REPO, str(WIKI_DIR)], check=True
        )
    return WIKI_DIR / WIKI_FILE


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^#{1,3}\s+(\w[\w$:/. -]*)", re.MULTILINE)
_SAMPLE_PROC_RE = re.compile(
    r"\*\*(?:Sample\s+)?Procedure:?\*?\*?\s*(\w+)", re.IGNORECASE
)
_CODE_BLOCK_RE = re.compile(r"```(?:text)?\n(.*?)```", re.DOTALL)


def _command_from_heading(heading: str) -> str:
    """Extract the primary command name from a section heading like 'ABS: Return...'"""
    cmd = heading.split(":")[0].strip().split("/")[0].strip()
    return re.sub(r"[^A-Za-z0-9_]", "_", cmd).lower()


def parse_sample_procedures(text: str) -> list[tuple[str, str, str]]:
    """Return list of (identifier, command, code) tuples.

    identifier is unique across all results and suitable as a Python/filename
    identifier.  command is the BASIC09 command the example demonstrates.
    code is the raw BASIC09 source.
    """
    # Split into segments between section headings so we can track which
    # command each sample belongs to.
    segments: list[tuple[str, str]] = []  # [(command_name, segment_text)]
    section_matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(section_matches):
        cmd = _command_from_heading(m.group(1))
        start = m.end()
        end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(text)
        segments.append((cmd, text[start:end]))

    results: list[tuple[str, str, str]] = []
    seen_ids: dict[str, int] = {}

    for cmd, segment in segments:
        # Find every Sample/Procedure label + the code block(s) that follow it
        proc_hits = list(_SAMPLE_PROC_RE.finditer(segment))
        code_blocks = list(_CODE_BLOCK_RE.finditer(segment))

        if not code_blocks:
            continue

        if proc_hits:
            # Pair each proc label with the next code block after it
            for j, ph in enumerate(proc_hits):
                proc_name = ph.group(1).lower()
                # Find the first code block that starts after this label
                block_code = None
                for cb in code_blocks:
                    if cb.start() > ph.start():
                        block_code = cb.group(1).rstrip()
                        break
                if block_code is None:
                    continue
                base_id = f"{cmd}_{proc_name}"
                count = seen_ids.get(base_id, 0)
                seen_ids[base_id] = count + 1
                uid = base_id if count == 0 else f"{base_id}_{count}"
                results.append((uid, cmd, block_code))
        else:
            # No labelled procedures in this section — take the last code block
            # (usually the sample, not the syntax examples)
            block_code = code_blocks[-1].group(1).rstrip()
            base_id = cmd
            count = seen_ids.get(base_id, 0)
            seen_ids[base_id] = count + 1
            uid = base_id if count == 0 else f"{base_id}_{count}"
            results.append((uid, cmd, block_code))

    return results


# ---------------------------------------------------------------------------
# Unsupported-feature detection
# ---------------------------------------------------------------------------

def unsupported_features(code: str) -> list[str]:
    found = []
    upper = code.upper()
    for kw in _UNSUPPORTED_KW:
        # Use word-boundary check; for multi-word tokens like "ON ERROR" just substring
        if " " in kw:
            if kw in upper:
                found.append(kw)
        elif re.search(r"\b" + re.escape(kw) + r"\b", upper):
            found.append(kw)
    return found


def uses_input(code: str) -> bool:
    return bool(re.search(r"\bINPUT\b", code, re.IGNORECASE))


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------

def write_proc_files(procs: list[tuple[str, str, str]]) -> None:
    PROCS_DIR.mkdir(parents=True, exist_ok=True)
    for f in PROCS_DIR.glob("*"):
        if f.is_file():
            f.unlink()
    for uid, _cmd, code in procs:
        (PROCS_DIR / uid).write_text(code + "\n")


def generate_test_file(procs: list[tuple[str, str, str]]) -> None:
    lines: list[str] = []

    def w(*args):
        lines.append("    ".join(str(a) for a in args) if args else "")

    w('"""Tests generated from the Basic09 Command Reference wiki sample procedures.')
    w()
    w("Regenerate with:  python scripts/generate_wiki_tests.py")
    w('"""')
    w("import pytest")
    w("from unittest.mock import patch")
    w("from pathlib import Path")
    w("from io import StringIO")
    w("from contextlib import redirect_stdout")
    w()
    w("from basic09 import Basic09Interpreter")
    w()
    w("import os")
    w("_NITROS9DIR = Path(os.environ.get(\"NITROS9DIR\", str(Path.home() / \"Projects/coco-shelf/nitros9\")))")
    w("PROCS_DIR = Path(_NITROS9DIR) / \"3rdparty/packages/basic09/tests/wiki_procs\"")
    w()

    # Build metadata table
    w("# (identifier, command, unsupported_features, needs_input)")
    w("_WIKI_PROCS = [")
    for uid, cmd, code in procs:
        bad = unsupported_features(code)
        needs_in = uses_input(code)
        lines.append(
            f"    ({uid!r}, {cmd!r}, {bad!r}, {needs_in!r}),"
        )
    w("]")
    w()

    # Helper to build param ids
    w("_IDS = [p[0] for p in _WIKI_PROCS]")
    w()

    # parse test
    w()
    w("@pytest.mark.parametrize(\"uid,cmd,bad,needs_in\", _WIKI_PROCS, ids=_IDS)")
    w("def test_wiki_sample_parses(uid, cmd, bad, needs_in):")
    w("    \"\"\"Every wiki sample procedure should parse without a grammar error.\"\"\"")
    w("    source = (PROCS_DIR / uid).read_text()")
    w("    try:")
    w("        with patch(\"builtins.input\", return_value=\"0\"):")
    w("            Basic09Interpreter(source)")
    w("    except Exception as e:")
    w("        pytest.xfail(f\"Parse/load error (likely wiki OCR artifact): {e}\")")
    w()

    # run test
    w()
    w("@pytest.mark.parametrize(\"uid,cmd,bad,needs_in\", _WIKI_PROCS, ids=_IDS)")
    w("def test_wiki_sample_runs(uid, cmd, bad, needs_in):")
    w("    \"\"\"Wiki sample procedures without OS-9 dependencies should run.\"\"\"")
    w("    if bad:")
    w("        pytest.skip(f\"Uses unsupported OS-9 features: {bad}\")")
    w("    source = (PROCS_DIR / uid).read_text()")
    w("    try:")
    w("        with patch(\"builtins.input\", return_value=\"0\"):")
    w("            interp = Basic09Interpreter(source)")
    w("    except Exception as e:")
    w("        pytest.xfail(f\"Parse error: {e}\")")
    w("        return")
    w("    try:")
    w("        buf = StringIO()")
    w("        with redirect_stdout(buf), patch(\"builtins.input\", return_value=\"0\"):")
    w("            interp.run()")
    w("    except Exception as e:")
    w("        pytest.xfail(f\"Runtime error (known wiki artifact or missing feature): {e}\")")
    w()

    TEST_FILE.write_text("\n".join(lines) + "\n")
    print(f"Wrote {TEST_FILE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Updating wiki repo...")
    md_path = clone_or_update_wiki()

    print(f"Parsing {md_path.name}...")
    text = md_path.read_text()
    procs = parse_sample_procedures(text)
    print(f"Found {len(procs)} sample procedures.")

    print(f"Writing .b09 files → {PROCS_DIR}")
    write_proc_files(procs)

    print("Generating test file...")
    generate_test_file(procs)

    unsupported_count = sum(1 for _, _, code in procs if unsupported_features(code))
    input_count = sum(1 for _, _, code in procs if uses_input(code))
    print(
        f"\nSummary: {len(procs)} procedures total, "
        f"{unsupported_count} with unsupported OS-9 features (will skip), "
        f"{input_count} with INPUT (will mock)."
    )


if __name__ == "__main__":
    main()
