#!/usr/bin/env python3
"""
Analyze nbgrader assignment fetch/submit events from an exported log CSV.

Input CSV (Kibana export) columns:
    "@timestamp", "kubernetes.pod.name", "message"

* pod name format:   jupyter-<username>-ml2026
* nbgrader request:  [I 2026-10-12 08:16:12.686 SingleUserLabApp log:191]
                     200 POST /user/luoz1/assignments/fetch?... (luoz1@IP) 142.45ms
                     (the older short form "[I ... /user/luoz1/assignments/fetch"
                     is still accepted)
* session start:     + mkdir -p /usr/local/bin/start-notebook-user.d/
* session end:       [C ... SingleUserLabApp serverapp:2127] received signal 15, stopping
* file save:         [I ... SingleUserLabApp handlers:184] Saving file at
                     /notebooks/ml2026/exam/exam.ipynb
                     (PUT/POST to /user/<user>/api/contents/ also accepted)

The script:
  1. lists students who fetched the assignment but never submitted it,
  2. prints a per-student summary (first fetch -> last submit, number of
     saves, time of last save, number of sessions and total time spent
     in sessions),
  3. pairs every session start with its signal-15 stop and reports the
     duration of each session,
  4. pairs every submit with the most recent fetch at or before it and
     reports the elapsed time.

Usage:
    python3 analyse_fetch_submit.py [csvfile] [--csv summary.csv]

Each output block can be selected; passing any block flag shows only the
selected blocks, --no-<flag> disables a single block:
    --missing / --no-missing      section 1 (fetched but never submitted)
    --summary / --no-summary      section 2 (per-student summary table)
    --sessions / --no-sessions    section 3 (session durations)
    --durations / --no-durations  section 4 (fetch -> submit durations)
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_CSV = (
    Path(__file__).resolve().parent / "exam1_ student start_fetch_save_submit_stop.csv"
)

POD_RE = re.compile(r"^jupyter-(?P<user>.+)-ml2026$")
# Matches both the old short form and the new full request-log line.
MSG_RE = re.compile(
    r"^\[[IWC]\s+(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r".*?/user/(?P<user>[^/]+)/assignments/(?P<action>fetch|submit)"
)
# Notebook file saves: "Saving file at /notebooks/..." (autosave) or
# PUT/POST to the contents API.
SAVE_RE = re.compile(
    r"^\[[IWC]\s+(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"(?:.*?Saving file at\s+|.*?(?:PUT|POST)\s+/user/[^/]+/api/contents/)"
)
# Timestamp embedded in a log message (the signal-15 lines carry one).
MSG_TS_RE = re.compile(r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)")
# Session start marker written by start-notebook-user.d
START_RE = re.compile(r"^\+\s*mkdir\s+-p\s+")
# Session end marker: the single-user server receives SIGTERM.
STOP_RE = re.compile(r"received signal 15")
KIBANA_TS_FMT = "%b %d, %Y @ %H:%M:%S.%f"
MSG_TS_FMT = "%Y-%m-%d %H:%M:%S.%f"

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)


def hl(text: str, code: str = "1;33") -> str:
    """Wrap text in ANSI colour when stdout is a terminal."""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def fmt_delta(delta: timedelta | None) -> str:
    """Format a timedelta as e.g. '1h 27m 05s'."""
    if delta is None:
        return "-"
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def username_from_pod(pod: str) -> str | None:
    """jupyter-<username>-ml2026 -> <username>"""
    m = POD_RE.match(pod.strip())
    return m.group("user") if m else None


def _kibana_ts(raw: str) -> datetime | None:
    """Parse a Kibana '@timestamp' value, returning None on failure."""
    try:
        return datetime.strptime(raw.strip(), KIBANA_TS_FMT)
    except ValueError:
        return None


def parse_row(row: dict) -> tuple[str, str, datetime] | None:
    """Return (username, action, timestamp) or None for unusable rows.

    Actions: "fetch"/"submit" (nbgrader requests), "start" (session start,
    the `mkdir -p` marker) and "stop" (session end, `signal 15`).
    """
    msg = (row.get("message") or "").strip()
    pod = row.get("kubernetes.pod.name") or ""
    raw = (row.get("@timestamp") or "").strip()

    # Session start marker: "+ mkdir -p /usr/local/bin/start-notebook-user.d/"
    if START_RE.match(msg):
        user = username_from_pod(pod)
        ts = _kibana_ts(raw)
        if user and ts:
            return user, "start", ts
        logger.info(f"parse_row: skipping start marker without user/timestamp: {msg}")
        return None

    # Session end marker: "received signal 15, stopping"
    if STOP_RE.search(msg):
        user = username_from_pod(pod)
        m = MSG_TS_RE.search(msg)
        ts = datetime.strptime(m.group("ts"), MSG_TS_FMT) if m else _kibana_ts(raw)
        if user and ts:
            return user, "stop", ts
        logger.info(f"parse_row: skipping stop marker without user/timestamp: {msg}")
        return None

    m = MSG_RE.match(msg)
    if m:
        # Prefer the username from the pod name, fall back to the one in the URL.
        user = username_from_pod(pod) or m.group("user")
        ts = datetime.strptime(m.group("ts"), MSG_TS_FMT)
        return user, m.group("action"), ts

    # Notebook saves: "Saving file at ..." or PUT/POST to the contents API.
    m = SAVE_RE.match(msg)
    if m:
        user = username_from_pod(pod)
        ts = datetime.strptime(m.group("ts"), MSG_TS_FMT)
        if user:
            return user, "save", ts
        logger.info(f"parse_row: skipping save without pod user: {msg}")
        return None

    # Fallback: derive the action from the message, time from @timestamp.
    if "/assignments/fetch" in msg:
        action = "fetch"
    elif "/assignments/submit" in msg:
        action = "submit"
    else:
        logger.info(f"parse_row: skipping row with unrecognized message: {msg}")
        return None
    user = username_from_pod(pod)
    if not user or not raw:
        logger.info(
            f"parse_row: skipping row with missing pod name or timestamp: {msg}"
        )
        return None
    ts = _kibana_ts(raw)
    if ts is None:
        logger.info(f"parse_row: skipping row with unparseable timestamp: {raw}")
        return None
    return user, action, ts


def load_events(path: Path) -> list[tuple[str, str, datetime]]:
    """Read the CSV and return sorted (username, action, timestamp) events."""
    events: list[tuple[str, str, datetime]] = []
    seen: set[tuple[str, str, datetime]] = set()
    # Session markers are logged twice (once per container) with ~1 ms skew,
    # so collapse repeats of the same marker within a one-second window.
    last_marker: dict[tuple[str, str], datetime] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            parsed = parse_row(row)
            if parsed is None:
                logger.info(f"load_events: could not parse row: {row}")
                continue
            user, action, ts = parsed
            if action in ("start", "stop"):
                key = (user, action)
                prev = last_marker.get(key)
                if prev and abs((ts - prev).total_seconds()) <= 1.0:
                    logger.info(
                        f"load_events: skipping duplicate {action} marker for {user}"
                    )
                    continue
                last_marker[key] = ts
            elif parsed in seen:  # duplicate log lines in the export
                logger.info(f"load_events: skipping duplicate row: {row}")
                continue
            else:
                seen.add(parsed)
            events.append(parsed)
    events.sort(key=lambda e: (e[2], e[0]))
    return events


def pair_sessions(
    starts: list[datetime], stops: list[datetime]
) -> list[tuple[datetime, datetime | None]]:
    """Pair each session start with the first stop after it.

    Returns a list of (start, stop) where stop is None when the session
    never ended within the log (server still running or log truncated).
    """
    sessions: list[tuple[datetime, datetime | None]] = []
    stops = sorted(stops)
    j = 0
    for st in sorted(starts):
        while j < len(stops) and stops[j] <= st:
            j += 1
        if j < len(stops):
            sessions.append((st, stops[j]))
            j += 1
        else:
            sessions.append((st, None))
    return sessions


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Report nbgrader fetch/submit activity per student."
    )
    ap.add_argument(
        "csvfile",
        nargs="?",
        default=str(DEFAULT_CSV),
        help=f"input CSV (default: {DEFAULT_CSV.name})",
    )
    ap.add_argument(
        "--csv", metavar="OUT", help="also write a per-student summary table to OUT"
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log skipped/duplicate rows while parsing",
    )
    ap.add_argument(
        "--missing",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="print section 1: students who fetched but never submitted",
    )
    ap.add_argument(
        "--summary",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="print section 2: per-student summary table",
    )
    ap.add_argument(
        "--sessions",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="print section 3: session start -> signal-15 durations",
    )
    ap.add_argument(
        "--durations",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="print section 4: fetch -> submit durations",
    )
    args = ap.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Block selection: with no block flags given, show everything. Passing
    # any positive flag (--missing etc.) selects only those blocks; --no-<flag>
    # removes a single block from the default set.
    blocks = {
        "missing": args.missing,
        "summary": args.summary,
        "sessions": args.sessions,
        "durations": args.durations,
    }
    if any(v is True for v in blocks.values()):
        show = {name for name, v in blocks.items() if v is True}
    else:
        show = {name for name, v in blocks.items() if v is not False}

    path = Path(args.csvfile)
    if not path.is_file():
        ap.error(f"no such file: {path}")

    events = load_events(path)
    if not events:
        ap.error("no fetch/submit events found in the file")

    per_user: dict[str, dict[str, list[datetime]]] = defaultdict(
        lambda: {"fetch": [], "submit": [], "save": [], "start": [], "stop": []}
    )
    for user, action, ts in events:
        per_user[user][action].append(ts)

    missing = never_submitted(per_user, show="missing" in show)

    summary = per_student(per_user, show="summary" in show)

    session_durations(summary, show="sessions" in show)

    fetch_to_submit(summary, show="durations" in show)

    n_sub = sum(1 for ev in per_user.values() if ev["submit"])
    n_open = sum(1 for row in summary if row[8])  # row[8] = open_sess
    print(
        f"Total: {len(per_user)} students, {n_sub} submitted, "
        f"{len(missing)} fetched without submitting, "
        f"{n_open} with a still-open session "
        f"({len(events)} log events after removing duplicates)."
    )

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "username",
                    "fetches",
                    "submits",
                    "saves",
                    "sessions",
                    "first_fetch",
                    "last_submit",
                    "last_save",
                    "total_first_fetch_to_last_submit",
                    "total_session_time",
                    "open_session",
                    "submitted",
                ]
            )
            for row in summary:
                _, u, ev, ff, ls, total, sessions, sess_total, open_sess, last_save = (
                    row
                )
                w.writerow(
                    [
                        u,
                        len(ev["fetch"]),
                        len(ev["submit"]),
                        len(ev["save"]),
                        len(sessions),
                        ff.isoformat() if ff else "",
                        ls.isoformat() if ls else "",
                        last_save.isoformat() if last_save else "",
                        fmt_delta(total) if total else "",
                        fmt_delta(sess_total) if sessions else "",
                        "yes" if open_sess else "",
                        "yes" if ls else "NO",
                    ]
                )
        print(f"Summary CSV written to {args.csv}")


def fetch_to_submit(summary, show: bool = True):
    # ---- 4. fetch -> submit durations ------------------------------------------
    if not show:
        return
    print("=" * 78)
    print("FETCH -> SUBMIT DURATIONS (each submit paired with the latest prior fetch)")
    print("=" * 78)
    for _, u, ev, *_ in summary:
        fetches = sorted(ev["fetch"])
        submits = sorted(ev["submit"])
        if not submits:
            print(hl(f"{u:<15}  fetched {len(fetches)}x, never submitted", "1;31"))
            continue
        for sub in submits:
            prior = [f for f in fetches if f <= sub]
            if prior:
                f = prior[-1]
                print(
                    f"{u:<15}  {f:%m-%d %H:%M:%S} -> {sub:%m-%d %H:%M:%S}"
                    f"  = {fmt_delta(sub - f)}"
                )
            else:
                print(
                    hl(
                        f"{u:<15}  {sub:%m-%d %H:%M:%S}  submit WITHOUT prior fetch",
                        "1;31",
                    )
                )
    print()


def session_durations(summary, show: bool = True):
    # ---- 3. session durations --------------------------------------------------
    if not show:
        return
    print("=" * 78)
    print("SESSIONS (start marker -> signal 15)")
    print("=" * 78)
    for _, u, ev, *_rest in summary:
        for st, sp in pair_sessions(ev["start"], ev["stop"]):
            if sp:
                print(
                    f"{u:<15}  {st:%m-%d %H:%M:%S} -> {sp:%m-%d %H:%M:%S}"
                    f"  = {fmt_delta(sp - st)}"
                )
            else:
                print(
                    hl(
                        f"{u:<15}  {st:%m-%d %H:%M:%S} -> still running / no stop event",
                        "1;33",
                    )
                )
    print()


def per_student(per_user, show: bool = True):
    # ---- 2. per-student summary ----------------------------------------------
    summary = []
    for u, ev in per_user.items():
        ff = min(ev["fetch"]) if ev["fetch"] else None
        ls = max(ev["submit"]) if ev["submit"] else None
        last_save = max(ev["save"]) if ev["save"] else None
        total = ls - ff if ff and ls else None
        sessions = pair_sessions(ev["start"], ev["stop"])
        sess_total = sum((sp - st for st, sp in sessions if sp), timedelta())
        open_sess = any(sp is None for st, sp in sessions)
        summary.append(
            (
                ff or ls or datetime.max,
                u,
                ev,
                ff,
                ls,
                total,
                sessions,
                sess_total,
                open_sess,
                last_save,
            )
        )
    summary.sort(key=lambda r: (r[0], r[1]))

    if show:
        print("=" * 78)
        print("PER-STUDENT SUMMARY (first fetch -> last submit, saves, session time)")
        print("=" * 78)
        header = (
            f"{'username':<15}{'fetch':>6}{'submit':>7}{'save':>6}{'sess':>6}  "
            f"{'first fetch':<17}{'last submit':<17}{'last save':<17}"
            f"{'total':>12}{'in sess':>12}"
        )
        print(header)
        print("-" * len(header))
        for row in summary:
            _, u, ev, ff, ls, total, sessions, sess_total, open_sess, last_save = row
            ff_s = f"{ff:%Y-%m-%d %H:%M}" if ff else "-"
            ls_s = f"{ls:%Y-%m-%d %H:%M}" if ls else "NEVER"
            save_s = f"{last_save:%m-%d %H:%M}" if last_save else "-"
            sess_s = fmt_delta(sess_total) if sessions else "-"
            if open_sess:
                sess_s += "+"
            line = (
                f"{u:<15}{len(ev['fetch']):>6}{len(ev['submit']):>7}"
                f"{len(ev['save']):>6}{len(sessions):>6}  "
                f"{ff_s:<17}{ls_s:<17}{save_s:<17}"
                f"{fmt_delta(total):>12}{sess_s:>12}"
            )
            print(hl(line, "1;31") if not ls else line)
        print()
    return summary


def never_submitted(per_user, show: bool = True):
    # ---- 1. students who fetched but never submitted -------------------------
    missing = sorted(
        u for u, ev in per_user.items() if ev["fetch"] and not ev["submit"]
    )
    if not show:
        return missing
    print("=" * 78)
    print(hl(f"FETCHED BUT NEVER SUBMITTED: {len(missing)} student(s)", "1;31"))
    print("=" * 78)
    if missing:
        for u in missing:
            first = min(per_user[u]["fetch"])
            print(
                hl(f"  !!! {u:<14} fetched {first:%Y-%m-%d %H:%M:%S}, no submit ever")
            )
    else:
        print("  (none - every student who fetched also submitted)")
    print()
    return missing


if __name__ == "__main__":
    main()
