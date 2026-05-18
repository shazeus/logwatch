"""Log analysis and statistics."""
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator, Optional

from logwatch.formats import LogEntry, detect_format, get_level_priority, parse_line


def iter_entries(
    path: Path,
    fmt: str = "auto",
    level_filter: Optional[str] = None,
    pattern: Optional[str] = None,
    invert: bool = False,
    tail: Optional[int] = None,
) -> Iterator[LogEntry]:
    regex = re.compile(pattern, re.IGNORECASE) if pattern else None
    min_priority = get_level_priority(level_filter) if level_filter else -1

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw_lines = fh.readlines()

    if fmt == "auto":
        fmt = detect_format(raw_lines[:100])

    if tail is not None:
        raw_lines = raw_lines[-tail:]
        start_lineno = max(1, len(raw_lines) - tail + 1)
    else:
        start_lineno = 1

    for idx, raw in enumerate(raw_lines, start=start_lineno):
        entry = parse_line(raw, idx, fmt)

        if min_priority >= 0 and get_level_priority(entry.level) < min_priority:
            continue

        if regex:
            matched = bool(regex.search(raw))
            if invert and matched:
                continue
            if not invert and not matched:
                continue

        yield entry


def compute_stats(path: Path, fmt: str = "auto") -> dict:
    level_counts: Counter = Counter()
    hour_counts: Counter = Counter()
    error_lines: list[str] = []
    total = 0
    ip_counts: Counter = Counter()
    status_counts: Counter = Counter()

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw_lines = fh.readlines()

    if fmt == "auto":
        fmt = detect_format(raw_lines[:100])

    for idx, raw in enumerate(raw_lines, 1):
        total += 1
        entry = parse_line(raw, idx, fmt)

        level_key = entry.level or "UNKNOWN"
        level_counts[level_key] += 1

        if entry.timestamp:
            hour_match = re.search(r"(\d{2}):\d{2}:\d{2}", entry.timestamp)
            if hour_match:
                hour_counts[int(hour_match.group(1))] += 1

        if entry.level in ("ERROR", "CRITICAL", "FATAL") and len(error_lines) < 10:
            error_lines.append(entry.raw)

        if "ip" in entry.extra and entry.extra["ip"]:
            ip_counts[entry.extra["ip"]] += 1
        if "status" in entry.extra and entry.extra["status"]:
            status_counts[entry.extra["status"]] += 1

    return {
        "total": total,
        "format": fmt,
        "level_counts": dict(level_counts),
        "hour_counts": dict(hour_counts),
        "top_errors": error_lines,
        "top_ips": ip_counts.most_common(10),
        "top_statuses": status_counts.most_common(10),
    }


def search_multi(
    paths: list[Path],
    pattern: str,
    fmt: str = "auto",
    level_filter: Optional[str] = None,
    invert: bool = False,
    context: int = 0,
) -> Iterator[tuple[Path, list[LogEntry]]]:
    for path in paths:
        if not path.exists():
            continue
        raw_lines: list[str] = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                raw_lines = fh.readlines()
        except OSError:
            continue

        detected_fmt = detect_format(raw_lines[:100]) if fmt == "auto" else fmt
        regex = re.compile(pattern, re.IGNORECASE)
        min_priority = get_level_priority(level_filter) if level_filter else -1
        results: list[LogEntry] = []

        for idx, raw in enumerate(raw_lines, 1):
            entry = parse_line(raw, idx, detected_fmt)

            if min_priority >= 0 and get_level_priority(entry.level) < min_priority:
                continue

            matched = bool(regex.search(raw))
            if not matched:
                continue

            if context > 0:
                start = max(0, idx - 1 - context)
                end = min(len(raw_lines), idx + context)
                ctx_entries = [
                    parse_line(raw_lines[i], i + 1, detected_fmt)
                    for i in range(start, end)
                ]
                results.extend(ctx_entries)
            else:
                results.append(entry)

        if results:
            yield path, results
