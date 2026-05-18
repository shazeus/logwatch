"""Log format detection and parsing."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

LEVEL_COLORS = {
    "ERROR": "red",
    "CRITICAL": "bold red",
    "FATAL": "bold red",
    "WARNING": "yellow",
    "WARN": "yellow",
    "INFO": "green",
    "DEBUG": "blue",
    "TRACE": "cyan",
    "NOTICE": "cyan",
}

LEVEL_PATTERNS = re.compile(
    r"\b(CRITICAL|FATAL|ERROR|WARNING|WARN|NOTICE|INFO|DEBUG|TRACE)\b",
    re.IGNORECASE,
)

FORMATS = {
    "syslog": re.compile(
        r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
        r"(?P<host>\S+)\s+(?P<service>\S+?)(?:\[(?P<pid>\d+)\])?:\s+(?P<message>.*)"
    ),
    "apache_combined": re.compile(
        r'(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
        r'"(?P<method>\w+)\s+(?P<path>\S+)\s+\S+"\s+(?P<status>\d+)\s+(?P<size>\S+)'
        r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?'
    ),
    "nginx": re.compile(
        r'(?P<ip>\S+)\s+-\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
        r'"(?P<method>\w+)\s+(?P<path>\S+)\s+\S+"\s+(?P<status>\d+)\s+(?P<size>\d+)'
    ),
    "python": re.compile(
        r"(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.]?\d*)\s+"
        r"(?P<level>\w+)\s+(?P<logger>\S+)\s+-\s+(?P<message>.*)"
    ),
    "json": re.compile(r"^\s*\{.*\}\s*$"),
    "iso8601": re.compile(
        r"(?P<time>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?)"
        r"\s+(?P<level>\w+)?\s*(?P<message>.*)"
    ),
    "nginx_error": re.compile(
        r"(?P<time>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[(?P<level>\w+)\]\s+(?P<message>.*)"
    ),
}


@dataclass
class LogEntry:
    raw: str
    line_number: int
    level: Optional[str] = None
    timestamp: Optional[str] = None
    message: Optional[str] = None
    format_name: Optional[str] = None
    extra: dict = field(default_factory=dict)

    @property
    def level_upper(self) -> str:
        return (self.level or "").upper()

    @property
    def color(self) -> str:
        return LEVEL_COLORS.get(self.level_upper, "white")


def detect_format(lines: list[str]) -> str:
    """Detect log format from sample lines."""
    counts = {name: 0 for name in FORMATS}
    sample = lines[:50]
    for line in sample:
        for name, pattern in FORMATS.items():
            if pattern.search(line):
                counts[name] += 1
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "generic"


def parse_line(line: str, line_number: int, fmt: str = "generic") -> LogEntry:
    entry = LogEntry(raw=line.rstrip(), line_number=line_number)

    level_match = LEVEL_PATTERNS.search(line)
    if level_match:
        entry.level = level_match.group(1).upper()

    if fmt in FORMATS:
        m = FORMATS[fmt].search(line)
        if m:
            entry.format_name = fmt
            gd = m.groupdict()
            entry.timestamp = gd.get("time")
            if "level" in gd and gd["level"]:
                entry.level = gd["level"].upper()
            entry.message = gd.get("message", line)
            entry.extra = {k: v for k, v in gd.items() if k not in ("time", "level", "message")}
            return entry

    entry.format_name = "generic"
    entry.message = line.rstrip()
    return entry


def get_level_priority(level: Optional[str]) -> int:
    priorities = {
        "TRACE": 0, "DEBUG": 1, "INFO": 2, "NOTICE": 3,
        "WARNING": 4, "WARN": 4, "ERROR": 5, "CRITICAL": 6, "FATAL": 6,
    }
    return priorities.get((level or "").upper(), 2)
