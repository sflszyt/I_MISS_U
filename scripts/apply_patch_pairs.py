#!/usr/bin/env python3
"""Apply LLM-produced "replacement pairs" to a single text file.

Usage
-----
    python scripts/apply_patch_pairs.py <target_file> <patch_file> [--dry-run]

Patch file format
-----------------
One or more blocks:

    <<<OLD>>>
    ...old snippet lines...
    <<<NEW>>>
    ...new snippet lines...
    <<<END>>>

Marker lines must be exactly ``<<<OLD>>>``, ``<<<NEW>>>`` and ``<<<END>>>``
(trailing whitespace and CR are ignored).  The OLD text is the block of lines
strictly between ``<<<OLD>>>`` and ``<<<NEW>>>`` joined with "\\n" (no trailing
newline is added); the NEW text is the block between ``<<<NEW>>>`` and
``<<<END>>>`` joined the same way.  NEW may be empty (pure deletion); OLD must
not be empty or whitespace-only.  Everything outside a block (prose, markdown
fences, ...) is ignored.  A structurally malformed patch, or a patch without
any block, is an error.  "\\r\\n" is normalised to "\\n" before parsing.

Behaviour
---------
* The target file is read as bytes; a UTF-8 BOM is remembered and stripped
  before the strict UTF-8 decode.
* The newline style is detected from the target (CRLF if "\\r\\n" occurs
  anywhere, otherwise LF) and the patch snippets are converted to it.
* Every pair is validated against the *original* content first: OLD must occur
  exactly once (overlapping matches are counted too) and the matched spans of
  different pairs must not overlap.  Any
  failure is reported to stderr and nothing is written.
* Replacements are applied from the end of the file towards the start, and the
  result is written atomically (temp file + os.replace), preserving the BOM and
  the newline style exactly.
* ``--dry-run`` performs the full validation and prints the summary and diff
  without writing anything.

Exit codes
----------
    0   success (including --dry-run)
    1   patch file / validation failure
    2   usage or I/O error (missing file, decode error, ...)
"""

from __future__ import annotations

import argparse
import codecs
import difflib
import os
import sys
import tempfile
from pathlib import Path

OLD_MARKER = "<<<OLD>>>"
NEW_MARKER = "<<<NEW>>>"
END_MARKER = "<<<END>>>"

BOM_UTF8 = codecs.BOM_UTF8


class PatchError(Exception):
    """Raised for a structurally malformed patch file."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(message)
        self.line = line
        self.message = message


def _configure_streams() -> None:
    """Make stdout/stderr usable on a Windows console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def parse_pairs(patch_text: str) -> list[tuple[str, str]]:
    """Parse the patch text into a list of (old, new) string pairs.

    ``patch_text`` must already have "\\r\\n" normalised to "\\n".
    Raises :class:`PatchError` (with the offending line number) on malformed
    structure.
    """
    lines = patch_text.split("\n")
    pairs: list[tuple[str, str]] = []

    state = "text"  # "text" | "old" | "new"
    old_lines: list[str] = []
    new_lines: list[str] = []
    old_line_no = 0

    for line_no, raw in enumerate(lines, start=1):
        marker = raw.rstrip()

        if marker == OLD_MARKER:
            if state != "text":
                raise PatchError(
                    line_no,
                    f"<<<OLD>>> while the block opened at line {old_line_no} is still open "
                    "(missing <<<END>>>)",
                )
            state = "old"
            old_lines = []
            new_lines = []
            old_line_no = line_no
            continue

        if marker == NEW_MARKER:
            if state != "old":
                raise PatchError(line_no, "<<<NEW>>> without a preceding <<<OLD>>>")
            state = "new"
            continue

        if marker == END_MARKER:
            if state != "new":
                raise PatchError(line_no, "<<<END>>> without a preceding <<<NEW>>>")
            old_text = "\n".join(old_lines)
            new_text = "\n".join(new_lines)
            if not old_text.strip():
                raise PatchError(old_line_no, "empty OLD snippet (needs at least one non-blank line)")
            pairs.append((old_text, new_text))
            state = "text"
            continue

        if state == "old":
            old_lines.append(raw)
        elif state == "new":
            new_lines.append(raw)
        # state == "text": everything outside a block is ignored.

    if state != "text":
        raise PatchError(old_line_no, "unterminated block (missing <<<END>>> before end of file)")

    return pairs


def first_nonblank_line(text: str, limit: int = 100) -> str:
    """Return ``repr`` of the first non-blank line of ``text``, truncated."""
    for line in text.split("\n"):
        if line.strip():
            rendered = repr(line)
            if len(rendered) > limit:
                rendered = rendered[: max(limit - 3, 0)] + "..."
            return rendered
    return repr("")


def count_occurrences(haystack: str, needle: str) -> int:
    """Count all occurrences, including overlapping ones (str.count finds non-overlapping only)."""
    if not needle:
        return 0
    count = 0
    start = 0
    while True:
        hit = haystack.find(needle, start)
        if hit == -1:
            return count
        count += 1
        start = hit + 1


def find_spans(
    content: str,
    pairs: list[tuple[str, str]],
    crlf: bool,
) -> tuple[list[tuple[int, int, int, str]], list[tuple[int, str, str]]]:
    """Locate every pair inside the original ``content``.

    Returns ``(spans, failures)`` where each span is
    ``(pair_index, start, end, new_text)`` and each failure is
    ``(pair_index, reason, first_nonblank_line_of_OLD)``.
    """
    convert = (lambda text: text.replace("\n", "\r\n")) if crlf else (lambda text: text)

    spans: list[tuple[int, int, int, str]] = []
    failures: list[tuple[int, str, str]] = []
    accepted: list[tuple[int, int, int]] = []

    for index, (old, new) in enumerate(pairs, start=1):
        old_text = convert(old)
        new_text = convert(new)

        count = count_occurrences(content, old_text)
        if count != 1:
            failures.append(
                (index, f"occurrence count {count} (expected exactly 1)", first_nonblank_line(old))
            )
            continue

        start = content.find(old_text)
        end = start + len(old_text)

        overlap = None
        for other_index, other_start, other_end in accepted:
            if start < other_end and other_start < end:
                overlap = other_index
                break

        if overlap is not None:
            failures.append((index, f"overlaps pair {overlap}", first_nonblank_line(old)))
            continue

        accepted.append((index, start, end))
        spans.append((index, start, end, new_text))

    return spans, failures


def apply_spans(content: str, spans: list[tuple[int, int, int, str]]) -> str:
    """Apply the (non-overlapping) spans, last one first, keeping offsets valid."""
    result = content
    for _index, start, end, new_text in sorted(spans, key=lambda span: span[1], reverse=True):
        result = result[:start] + new_text + result[end:]
    return result


def write_atomic(target_file: str, text: str, has_bom: bool) -> None:
    """Write ``text`` (UTF-8, exact newlines) atomically over ``target_file``."""
    data = text.encode("utf-8")
    if has_bom:
        data = BOM_UTF8 + data

    target_dir = os.path.dirname(os.path.abspath(target_file)) or "."
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=target_dir)
    tmp_path = tmp.name
    try:
        try:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp_path, target_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def unified_diff_lines(old_text: str, new_text: str, target_file: str) -> list[str]:
    """Build a unified diff over LF-normalised lines (line endings removed)."""
    name = os.path.basename(target_file)
    old_lines = old_text.replace("\r\n", "\n").split("\n")
    new_lines = new_text.replace("\r\n", "\n").split("\n")
    return list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            lineterm="",
        )
    )


def main(argv: list[str] | None = None) -> int:
    _configure_streams()

    parser = argparse.ArgumentParser(
        prog="apply_patch_pairs.py",
        description="Apply LLM-produced <<<OLD>>>/<<<NEW>>>/<<<END>>> replacement pairs to one file.",
    )
    parser.add_argument("target_file", help="text file to patch")
    parser.add_argument("patch_file", help="file containing the replacement-pair blocks")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and show the diff without writing the target file",
    )
    args = parser.parse_args(argv)

    # ---- read and decode the target ------------------------------------
    try:
        raw = Path(args.target_file).read_bytes()
    except OSError as exc:
        print(f"error: cannot read target file {args.target_file!r}: {exc}", file=sys.stderr)
        return 2

    has_bom = raw.startswith(BOM_UTF8)
    if has_bom:
        raw = raw[len(BOM_UTF8):]

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"error: target file {args.target_file!r} is not valid UTF-8: {exc}", file=sys.stderr)
        return 2

    # ---- read and parse the patch --------------------------------------
    try:
        patch_bytes = Path(args.patch_file).read_bytes()
    except OSError as exc:
        print(f"error: cannot read patch file {args.patch_file!r}: {exc}", file=sys.stderr)
        return 2

    try:
        patch_text = patch_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        print(f"error: patch file {args.patch_file!r} is not valid UTF-8: {exc}", file=sys.stderr)
        return 2

    patch_text = patch_text.replace("\r\n", "\n")

    try:
        pairs = parse_pairs(patch_text)
    except PatchError as exc:
        print(f"error: {args.patch_file}: line {exc.line}: {exc.message}", file=sys.stderr)
        return 1

    if not pairs:
        print(
            f"error: {args.patch_file}: no <<<OLD>>>/<<<NEW>>>/<<<END>>> blocks found",
            file=sys.stderr,
        )
        return 1

    # ---- validate everything against the original content --------------
    crlf = "\r\n" in content
    spans, failures = find_spans(content, pairs, crlf)
    if failures:
        for index, reason, snippet in failures:
            print(f"pair {index}: {reason}; OLD first line: {snippet}", file=sys.stderr)
        return 1

    new_content = apply_spans(content, spans)

    # ---- write or report ------------------------------------------------
    if args.dry_run:
        print(f"dry-run: {len(pairs)} pair(s) would apply to {args.target_file}")
    else:
        try:
            write_atomic(args.target_file, new_content, has_bom)
        except OSError as exc:
            print(f"error: cannot write target file {args.target_file!r}: {exc}", file=sys.stderr)
            return 2
        print(f"applied {len(pairs)} pair(s) to {args.target_file}")

    diff_lines = unified_diff_lines(content, new_content, args.target_file)
    if diff_lines:
        sys.stdout.write("\n".join(diff_lines) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
