"""logwatch CLI — real-time log analyzer and monitor."""
import re
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import click
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from logwatch import __version__
from logwatch.analyzer import compute_stats, iter_entries, search_multi
from logwatch.formats import LEVEL_COLORS, LogEntry, detect_format, get_level_priority

console = Console()
err_console = Console(stderr=True)

LEVEL_CHOICES = click.Choice(
    ["TRACE", "DEBUG", "INFO", "NOTICE", "WARNING", "WARN", "ERROR", "CRITICAL", "FATAL"],
    case_sensitive=False,
)


def _render_entry(entry: LogEntry, show_lineno: bool = False, filename: Optional[str] = None) -> Text:
    t = Text()
    if filename:
        t.append(f"{filename}:", style="dim")
    if show_lineno:
        t.append(f"{entry.line_number:>6}: ", style="dim")
    if entry.timestamp:
        t.append(f"[{entry.timestamp}] ", style="dim cyan")
    if entry.level:
        color = LEVEL_COLORS.get(entry.level.upper(), "white")
        t.append(f"{entry.level:<8} ", style=f"bold {color}")
    t.append(entry.message or entry.raw)
    return t


@click.group()
@click.version_option(__version__, prog_name="logwatch")
def cli():
    """logwatch — real-time log file analyzer and monitor."""


# ──────────────────────────────────────────────────────
# logwatch tail
# ──────────────────────────────────────────────────────
@cli.command("tail")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-n", "--lines", default=20, show_default=True, help="Lines to show before following.")
@click.option("-l", "--level", default=None, type=LEVEL_CHOICES, help="Minimum log level to show.")
@click.option("-p", "--pattern", default=None, help="Regex pattern to filter lines.")
@click.option("--invert", is_flag=True, help="Invert pattern match.")
@click.option("-f", "--follow", is_flag=True, default=True, help="Follow file for new lines.")
@click.option("--no-follow", is_flag=True, help="Print tail only, don't follow.")
@click.option("--fmt", default="auto", help="Log format override.")
def tail_cmd(files, lines, level, pattern, invert, follow, no_follow, fmt):
    """Tail and optionally follow one or more log files in real time."""
    paths = [Path(f) for f in files]
    multi = len(paths) > 1

    for path in paths:
        if multi:
            console.rule(f"[bold]{path.name}")
        for entry in iter_entries(path, fmt=fmt, level_filter=level, pattern=pattern,
                                   invert=invert, tail=lines):
            console.print(_render_entry(entry, show_lineno=False))

    if no_follow or not follow:
        return

    console.rule("[dim]following…")

    from logwatch.watcher import watch_files

    stop = threading.Event()

    def on_line(path: Path, line: str, lineno: int):
        from logwatch.formats import parse_line
        entry = parse_line(line, lineno, fmt if fmt != "auto" else "generic")
        prefix = f"{path.name}: " if multi else None
        console.print(_render_entry(entry, show_lineno=False, filename=prefix and path.name))

    try:
        watch_files(paths, on_line, pattern=pattern, level_filter=level, invert=invert,
                    stop_event=stop)
    except KeyboardInterrupt:
        stop.set()


# ──────────────────────────────────────────────────────
# logwatch search
# ──────────────────────────────────────────────────────
@cli.command("search")
@click.argument("pattern")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-l", "--level", default=None, type=LEVEL_CHOICES, help="Minimum log level.")
@click.option("--invert", is_flag=True, help="Show lines NOT matching pattern.")
@click.option("-c", "--context", default=0, help="Lines of context around match.", show_default=True)
@click.option("--fmt", default="auto", help="Log format override.")
@click.option("--count", is_flag=True, help="Print match count only.")
def search_cmd(pattern, files, level, invert, context, fmt, count):
    """Search log files for a regex PATTERN."""
    paths = [Path(f) for f in files]
    total_matches = 0

    for path, entries in search_multi(paths, pattern, fmt=fmt, level_filter=level,
                                       invert=invert, context=context):
        if count:
            total_matches += len(entries)
            console.print(f"{path}: [bold]{len(entries)}[/bold] match(es)")
        else:
            if len(paths) > 1:
                console.rule(f"[bold]{path.name}")
            for entry in entries:
                console.print(_render_entry(entry, show_lineno=True))
            total_matches += len(entries)

    if count:
        console.print(f"\nTotal: [bold green]{total_matches}[/bold green] match(es)")
    elif total_matches == 0:
        console.print("[yellow]No matches found.[/yellow]")


# ──────────────────────────────────────────────────────
# logwatch stats
# ──────────────────────────────────────────────────────
@cli.command("stats")
@click.argument("file", type=click.Path(exists=True))
@click.option("--fmt", default="auto", help="Log format override.")
def stats_cmd(file, fmt):
    """Show statistics and summary for a log file."""
    path = Path(file)
    with console.status(f"[bold green]Analyzing {path.name}…"):
        stats = compute_stats(path, fmt=fmt)

    console.print(Panel(
        f"[bold]{path.name}[/bold]  |  "
        f"[dim]Format:[/dim] [cyan]{stats['format']}[/cyan]  |  "
        f"[dim]Lines:[/dim] [green]{stats['total']:,}[/green]",
        title="[bold blue]logwatch stats",
        expand=False,
    ))

    # Level breakdown
    level_table = Table(title="Log Levels", show_header=True, header_style="bold magenta")
    level_table.add_column("Level", style="bold")
    level_table.add_column("Count", justify="right")
    level_table.add_column("Bar")
    total = max(stats["total"], 1)
    for lvl, cnt in sorted(stats["level_counts"].items(),
                            key=lambda x: get_level_priority(x[0]), reverse=True):
        color = LEVEL_COLORS.get(lvl.upper(), "white")
        bar_len = int((cnt / total) * 40)
        bar = f"[{color}]{'█' * bar_len}[/{color}]"
        level_table.add_row(Text(lvl, style=f"bold {color}"), f"{cnt:,}", bar)
    console.print(level_table)

    # Hourly distribution
    if stats["hour_counts"]:
        hour_table = Table(title="Activity by Hour (UTC)", show_header=True,
                           header_style="bold magenta")
        hour_table.add_column("Hour", justify="center")
        hour_table.add_column("Lines", justify="right")
        hour_table.add_column("Distribution")
        max_hour = max(stats["hour_counts"].values()) or 1
        for h in range(24):
            cnt = stats["hour_counts"].get(h, 0)
            bar_len = int((cnt / max_hour) * 30)
            bar = f"[cyan]{'▌' * bar_len}[/cyan]" if bar_len else ""
            hour_table.add_row(f"{h:02d}:xx", f"{cnt:,}", bar)
        console.print(hour_table)

    # Top IPs
    if stats["top_ips"]:
        ip_table = Table(title="Top Client IPs", show_header=True, header_style="bold magenta")
        ip_table.add_column("IP")
        ip_table.add_column("Requests", justify="right")
        for ip, cnt in stats["top_ips"]:
            ip_table.add_row(ip, f"{cnt:,}")
        console.print(ip_table)

    # Top HTTP statuses
    if stats["top_statuses"]:
        status_table = Table(title="HTTP Status Codes", show_header=True,
                              header_style="bold magenta")
        status_table.add_column("Status")
        status_table.add_column("Count", justify="right")
        for st, cnt in stats["top_statuses"]:
            color = "green" if st.startswith("2") else "yellow" if st.startswith("3") else "red"
            status_table.add_row(Text(st, style=f"bold {color}"), f"{cnt:,}")
        console.print(status_table)

    # Recent errors
    if stats["top_errors"]:
        console.print(Panel(
            "\n".join(
                f"[red]{e[:120]}[/red]" if len(e) <= 120 else f"[red]{e[:117]}…[/red]"
                for e in stats["top_errors"]
            ),
            title="[bold red]Recent Errors (up to 10)",
            border_style="red",
        ))


# ──────────────────────────────────────────────────────
# logwatch filter
# ──────────────────────────────────────────────────────
@cli.command("filter")
@click.argument("file", type=click.Path(exists=True))
@click.option("-l", "--level", required=True, type=LEVEL_CHOICES, help="Minimum level to show.")
@click.option("-p", "--pattern", default=None, help="Additional regex filter.")
@click.option("--invert", is_flag=True, help="Invert pattern.")
@click.option("-n", "--lines", default=None, type=int, help="Show last N lines only.")
@click.option("--fmt", default="auto", help="Log format override.")
@click.option("-o", "--output", default=None, type=click.Path(), help="Write filtered output to file.")
def filter_cmd(file, level, pattern, invert, lines, fmt, output):
    """Filter log entries by level and/or regex pattern."""
    path = Path(file)
    entries = list(iter_entries(path, fmt=fmt, level_filter=level, pattern=pattern,
                                 invert=invert, tail=lines))

    out_lines = []
    for entry in entries:
        rendered = _render_entry(entry, show_lineno=True)
        console.print(rendered)
        out_lines.append(entry.raw)

    if output:
        Path(output).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        console.print(f"\n[green]Wrote {len(out_lines)} lines → {output}[/green]")

    console.print(f"\n[dim]{len(entries)} entries shown[/dim]")


# ──────────────────────────────────────────────────────
# logwatch detect
# ──────────────────────────────────────────────────────
@cli.command("detect")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
def detect_cmd(files):
    """Auto-detect the format of one or more log files."""
    table = Table(title="Log Format Detection", header_style="bold magenta", show_lines=True)
    table.add_column("File")
    table.add_column("Detected Format", style="bold cyan")
    table.add_column("Lines Sampled", justify="right")
    table.add_column("Sample Line", no_wrap=False, max_width=60)

    for f in files:
        path = Path(f)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                sample = [fh.readline() for _ in range(100)]
            fmt = detect_format(sample)
            first_line = next((l.strip() for l in sample if l.strip()), "")
            table.add_row(
                path.name,
                fmt,
                str(sum(1 for l in sample if l)),
                first_line[:80],
            )
        except OSError as e:
            table.add_row(path.name, "[red]ERROR[/red]", "0", str(e))

    console.print(table)


# ──────────────────────────────────────────────────────
# logwatch watch
# ──────────────────────────────────────────────────────
@cli.command("watch")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-l", "--level", default=None, type=LEVEL_CHOICES, help="Minimum level.")
@click.option("-p", "--pattern", default=None, help="Regex to filter incoming lines.")
@click.option("--invert", is_flag=True, help="Invert pattern.")
@click.option("--alert-level", default="ERROR", type=LEVEL_CHOICES,
              help="Flash panel on lines >= this level.", show_default=True)
@click.option("--fmt", default="auto", help="Log format.")
def watch_cmd(files, level, pattern, invert, alert_level, fmt):
    """Watch log files live and highlight critical events."""
    from logwatch.formats import parse_line
    from logwatch.watcher import watch_files

    paths = [Path(f) for f in files]
    multi = len(paths) > 1
    alert_priority = get_level_priority(alert_level)
    stop = threading.Event()
    seen_count = Counter()

    console.print(Panel(
        "[bold green]Watching files for new log entries…[/bold green]\n"
        f"Files: {', '.join(str(p) for p in paths)}\n"
        f"Alert threshold: [bold red]{alert_level}[/bold red]\n"
        "Press [bold]Ctrl+C[/bold] to stop.",
        title="[bold blue]logwatch watch",
    ))

    def on_line(path: Path, line: str, lineno: int):
        entry = parse_line(line, lineno, "generic")
        seen_count["total"] += 1
        if entry.level and get_level_priority(entry.level) >= alert_priority:
            seen_count["alerts"] += 1
            color = LEVEL_COLORS.get(entry.level, "red")
            console.print(Panel(
                _render_entry(entry, show_lineno=False, filename=path.name if multi else None),
                border_style=color,
                title=f"[bold {color}]ALERT: {entry.level}[/bold {color}]",
            ))
        else:
            console.print(_render_entry(entry, show_lineno=False,
                                         filename=path.name if multi else None))

    try:
        watch_files(paths, on_line, pattern=pattern, level_filter=level,
                    invert=invert, stop_event=stop)
    except KeyboardInterrupt:
        stop.set()
        console.print(f"\n[dim]Session ended — {seen_count['total']} lines seen, "
                      f"{seen_count['alerts']} alerts.[/dim]")


# ──────────────────────────────────────────────────────
# logwatch errors
# ──────────────────────────────────────────────────────
@cli.command("errors")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-n", "--limit", default=50, show_default=True, help="Max errors to display.")
@click.option("--fmt", default="auto", help="Log format override.")
@click.option("--since", default=None, help="Show errors after this timestamp string (substring match).")
def errors_cmd(files, limit, fmt, since):
    """Extract and display only error/critical entries from log files."""
    for f in files:
        path = Path(f)
        if len(files) > 1:
            console.rule(f"[bold]{path.name}")

        count = 0
        for entry in iter_entries(path, fmt=fmt, level_filter="ERROR"):
            if since and entry.timestamp and since not in (entry.timestamp or ""):
                continue
            console.print(_render_entry(entry, show_lineno=True))
            count += 1
            if count >= limit:
                console.print(f"[dim]… limit of {limit} reached[/dim]")
                break

        console.print(f"[green]{count}[/green] error(s) shown from [bold]{path.name}[/bold]\n")


# ──────────────────────────────────────────────────────
# logwatch diff
# ──────────────────────────────────────────────────────
@cli.command("diff")
@click.argument("file_a", type=click.Path(exists=True))
@click.argument("file_b", type=click.Path(exists=True))
@click.option("--fmt", default="auto", help="Log format override.")
def diff_cmd(file_a, file_b, fmt):
    """Compare level distribution between two log files."""
    pa, pb = Path(file_a), Path(file_b)

    with console.status("Analyzing files…"):
        stats_a = compute_stats(pa, fmt)
        stats_b = compute_stats(pb, fmt)

    table = Table(title=f"Level Diff: {pa.name} vs {pb.name}", header_style="bold magenta",
                  show_lines=True)
    table.add_column("Level")
    table.add_column(pa.name, justify="right")
    table.add_column(pb.name, justify="right")
    table.add_column("Delta", justify="right")

    all_levels = sorted(
        set(stats_a["level_counts"]) | set(stats_b["level_counts"]),
        key=get_level_priority, reverse=True,
    )
    for lvl in all_levels:
        ca = stats_a["level_counts"].get(lvl, 0)
        cb = stats_b["level_counts"].get(lvl, 0)
        delta = cb - ca
        color = LEVEL_COLORS.get(lvl.upper(), "white")
        delta_str = (
            f"[green]+{delta}[/green]" if delta > 0
            else f"[red]{delta}[/red]" if delta < 0
            else "[dim]0[/dim]"
        )
        table.add_row(Text(lvl, style=f"bold {color}"), str(ca), str(cb), delta_str)

    console.print(table)
    console.print(
        f"\n[dim]Total lines: {pa.name}=[bold]{stats_a['total']:,}[/bold]  "
        f"{pb.name}=[bold]{stats_b['total']:,}[/bold][/dim]"
    )
