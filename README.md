<p align="center">
  <h1 align="center">logwatch</h1>
  <p align="center">Real-time log file analyzer and monitor for the terminal.</p>
  <p align="center">
    <a href="https://pypi.org/project/logwatch-cli/"><img src="https://img.shields.io/pypi/v/logwatch-cli?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/logwatch-cli/"><img src="https://img.shields.io/pypi/pyversions/logwatch-cli" alt="Python"></a>
    <a href="https://github.com/shazeus/logwatch/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
    <a href="https://github.com/shazeus/logwatch/stargazers"><img src="https://img.shields.io/github/stars/shazeus/logwatch?style=social" alt="Stars"></a>
  </p>
</p>

---

**logwatch** is a powerful, zero-configuration CLI tool for monitoring and analyzing log files in real time. It auto-detects common log formats (syslog, Apache/Nginx, Python, ISO 8601, and more), filters by severity level, searches with regex, and renders beautiful terminal output powered by Rich.

- **Auto-format detection** — identifies syslog, Apache combined, Nginx, Python logging, ISO 8601, and generic formats automatically
- **Real-time tail & watch** — follow files live with `tail -f`-like behavior; receive visual alerts on ERROR/CRITICAL lines
- **Level filtering** — show only WARN, ERROR, CRITICAL, etc. with color-coded output
- **Regex search** — grep across one or many log files with context lines and invert support
- **Statistics & visualization** — bar charts of level distribution, hourly activity heatmap, top IPs, HTTP status breakdown
- **Multi-file support** — all commands accept multiple files and label output per source
- **Error extraction** — quickly dump all error/critical lines from any log
- **Log diff** — compare level distributions between two log snapshots

## Installation

```bash
pip install logwatch-cli
```

**Requirements:** Python 3.10+

## Usage

```bash
# Tail last 20 lines and follow live
logwatch tail /var/log/syslog

# Follow multiple files, only WARN+
logwatch tail -l WARNING /var/log/nginx/access.log /var/log/nginx/error.log

# Search for pattern across logs
logwatch search "connection refused" /var/log/*.log

# Show statistics for a log file
logwatch stats /var/log/apache2/access.log

# Filter to ERROR+ and write to file
logwatch filter -l ERROR /var/log/app.log -o errors.log

# Watch live with alert panels for ERROR+
logwatch watch /var/log/app.log --alert-level ERROR

# Extract only errors
logwatch errors /var/log/syslog -n 100

# Detect log format
logwatch detect /var/log/syslog /var/log/nginx/access.log

# Compare two log files
logwatch diff /var/log/app.log.1 /var/log/app.log
```

## Commands

| Command | Description |
|---------|-------------|
| `tail` | Tail log file(s) and optionally follow live (`-f` default on) |
| `watch` | Live watch with rich alert panels for critical events |
| `search` | Regex search across one or many log files |
| `filter` | Filter by log level and/or regex, export filtered output |
| `stats` | Full statistics: levels, hourly heatmap, top IPs, status codes |
| `errors` | Extract and show only ERROR/CRITICAL entries |
| `detect` | Auto-detect the format of log files |
| `diff` | Compare level distributions between two log files |

### Common Options

| Flag | Description |
|------|-------------|
| `-l / --level` | Minimum log level (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `-p / --pattern` | Regex filter pattern |
| `--invert` | Invert pattern match (exclude matching lines) |
| `-n / --lines` | Number of lines for `tail` and `filter` |
| `-n / --limit` | Maximum entries for `errors` |
| `--fmt` | Override format detection (auto, syslog, python, apache_combined, nginx, iso8601) |
| `--no-follow` | Print tail only, don't follow |

## Configuration

No configuration file required. logwatch works out of the box. Pipe-friendly — all output goes to stdout; combine with standard Unix tools as needed.

```bash
# Pipe filtered output to less
logwatch filter -l ERROR /var/log/app.log | less -R

# Count errors per file
logwatch search "ERROR" /var/log/*.log --count
```

## License

MIT © [shazeus](https://github.com/shazeus)
