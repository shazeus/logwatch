"""Real-time file watching using watchdog + manual tail."""
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer


class TailHandler(FileSystemEventHandler):
    def __init__(
        self,
        path: Path,
        callback: Callable[[str, int], None],
        pattern: Optional[str] = None,
        level_filter: Optional[str] = None,
        invert: bool = False,
    ):
        self.path = path
        self.callback = callback
        self.regex = re.compile(pattern, re.IGNORECASE) if pattern else None
        self.level_filter = (level_filter or "").upper()
        self.invert = invert
        self._pos = path.stat().st_size if path.exists() else 0
        self._lineno = self._count_lines()
        self._lock = threading.Lock()

        from logwatch.formats import LEVEL_PATTERNS, get_level_priority
        self._LEVEL_PATTERNS = LEVEL_PATTERNS
        self._get_level_priority = get_level_priority
        self._min_priority = get_level_priority(level_filter) if level_filter else -1

    def _count_lines(self) -> int:
        if not self.path.exists():
            return 0
        try:
            with open(self.path, "rb") as fh:
                return sum(1 for _ in fh)
        except OSError:
            return 0

    def on_modified(self, event):
        if not isinstance(event, FileModifiedEvent):
            return
        if Path(event.src_path).resolve() != self.path.resolve():
            return
        self._read_new()

    def _read_new(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
                    fh.seek(self._pos)
                    new_data = fh.read()
                    self._pos = fh.tell()
            except OSError:
                return

            for line in new_data.splitlines():
                if not line.strip():
                    continue
                self._lineno += 1
                if not self._passes_filters(line):
                    continue
                self.callback(line, self._lineno)

    def _passes_filters(self, line: str) -> bool:
        if self._min_priority >= 0:
            level_match = self._LEVEL_PATTERNS.search(line)
            level = level_match.group(1).upper() if level_match else None
            if self._get_level_priority(level) < self._min_priority:
                return False

        if self.regex:
            matched = bool(self.regex.search(line))
            if self.invert and matched:
                return False
            if not self.invert and not matched:
                return False

        return True


def watch_files(
    paths: list[Path],
    callback: Callable[[Path, str, int], None],
    pattern: Optional[str] = None,
    level_filter: Optional[str] = None,
    invert: bool = False,
    stop_event: Optional[threading.Event] = None,
):
    observer = Observer()
    handlers: list[TailHandler] = []

    for path in paths:
        if not path.exists():
            continue

        def make_cb(p: Path) -> Callable[[str, int], None]:
            def cb(line: str, lineno: int) -> None:
                callback(p, line, lineno)
            return cb

        handler = TailHandler(path, make_cb(path), pattern, level_filter, invert)
        handlers.append(handler)
        observer.schedule(handler, str(path.parent), recursive=False)

    observer.start()
    try:
        while not (stop_event and stop_event.is_set()):
            time.sleep(0.2)
    finally:
        observer.stop()
        observer.join()
