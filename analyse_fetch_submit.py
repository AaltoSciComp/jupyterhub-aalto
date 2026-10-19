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
import enum
import logging
import re
import sys
from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from pathlib import Path

# One parsed log event: "fetch"/"submit"/"save" request or "start"/"stop"
# session marker.
Event = namedtuple("Event", ["user", "action", "ts"])

# A session: start marker paired with the first following signal-15 stop
# (stop is None when the session never ended within the log).
Session = namedtuple("Session", ["start", "stop"])

# Per-student aggregate used for the summary table and CSV export.
StudentSummary = namedtuple(
    "StudentSummary",
    [
        "sort_key",  # first fetch (or last submit, or datetime.max)
        "user",
        "events",  # dict of action -> list[datetime]
        "first_fetch",
        "last_submit",
        "total",  # first fetch -> last submit
        "sessions",  # list[Session]
        "sess_total",  # sum of closed session durations
        "open_session",  # True if any session has no stop
        "last_save",
    ],
)

DEFAULT_CSV = (
    Path(__file__).resolve().parent / "exam1_ student start_fetch_save_submit_stop2.csv"
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


class Colours(enum.Enum):
    RED = "1;31"
    YELLOW = "1;33"
    GREEN = "1;32"
    CYAN = "1;36"


def hl(text: str, code: Colours = Colours.YELLOW) -> str:
    """Wrap text in ANSI colour when stdout is a terminal."""
    if sys.stdout.isatty():
        return f"\033[{code.value}m{text}\033[0m"
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


def parse_row(row: dict) -> Event | None:
    """Return an Event or None for unusable rows.

    Actions: "fetch"/"submit" (nbgrader requests), "save" (file saves),
    "start" (session start, the `mkdir -p` marker) and "stop" (session end,
    `signal 15`).
    """
    msg = (row.get("message") or "").strip()
    pod = row.get("kubernetes.pod.name") or ""
    raw = (row.get("@timestamp") or "").strip()

    # Session start marker: "+ mkdir -p /usr/local/bin/start-notebook-user.d/"
    if START_RE.match(msg):
        user = username_from_pod(pod)
        ts = _kibana_ts(raw)
        if user and ts:
            return Event(user, "start", ts)
        logger.info(f"parse_row: skipping start marker without user/timestamp: {msg}")
        return None

    # Session end marker: "received signal 15, stopping"
    if STOP_RE.search(msg):
        user = username_from_pod(pod)
        m = MSG_TS_RE.search(msg)
        ts = datetime.strptime(m.group("ts"), MSG_TS_FMT) if m else _kibana_ts(raw)
        if user and ts:
            return Event(user, "stop", ts)
        logger.info(f"parse_row: skipping stop marker without user/timestamp: {msg}")
        return None

    m = MSG_RE.match(msg)
    if m:
        # Prefer the username from the pod name, fall back to the one in the URL.
        user = username_from_pod(pod) or m.group("user")
        ts = datetime.strptime(m.group("ts"), MSG_TS_FMT)
        return Event(user, m.group("action"), ts)

    # Notebook saves: "Saving file at ..." or PUT/POST to the contents API.
    m = SAVE_RE.match(msg)
    if m:
        user = username_from_pod(pod)
        ts = datetime.strptime(m.group("ts"), MSG_TS_FMT)
        if user:
            return Event(user, "save", ts)
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
    return Event(user, action, ts)


def load_events(path: Path) -> list[Event]:
    """Read the CSV and return sorted Event tuples."""
    events: list[Event] = []
    seen: set[Event] = set()
    # Session markers are logged twice (once per container) with ~1 ms skew,
    # so collapse repeats of the same marker within a one-second window.
    last_marker: dict[tuple[str, str], datetime] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            parsed = parse_row(row)
            if parsed is None:
                logger.info(f"load_events: could not parse row: {row}")
                continue
            if parsed.action in ("start", "stop"):
                key = (parsed.user, parsed.action)
                prev = last_marker.get(key)
                if prev and abs((parsed.ts - prev).total_seconds()) <= 1.0:
                    logger.info(
                        f"load_events: skipping duplicate {parsed.action} marker "
                        f"for {parsed.user}"
                    )
                    continue
                last_marker[key] = parsed.ts
            elif parsed in seen:  # duplicate log lines in the export
                logger.info(f"load_events: skipping duplicate row: {row}")
                continue
            else:
                seen.add(parsed)
            events.append(parsed)
    events.sort(key=lambda e: (e.ts, e.user))
    return events


def pair_sessions(starts: list[datetime], stops: list[datetime]) -> list[Session]:
    """Pair each session start with the first stop after it.

    Returns a list of Session tuples where stop is None when the session
    never ended within the log (server still running or log truncated).
    """
    sessions: list[Session] = []
    stops = sorted(stops)
    j = 0
    for st in sorted(starts):
        while j < len(stops) and stops[j] <= st:
            j += 1
        if j < len(stops):
            sessions.append(Session(st, stops[j]))
            j += 1
        else:
            sessions.append(Session(st, None))
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
    ap.add_argument(
        "--unsubmitted-only",
        action="store_true",
        default=False,
        help="In the summary, only show students who fetched but never submitted",
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
    for event in events:
        per_user[event.user][event.action].append(event.ts)

    missing = never_submitted(per_user, show="missing" in show)

    summary = per_student(
        per_user, show="summary" in show, unsubmitted_only=args.unsubmitted_only
    )

    session_durations(summary, show="sessions" in show)

    fetch_to_submit(summary, show="durations" in show)

    n_sub = sum(1 for ev in per_user.values() if ev["submit"])
    n_open = sum(1 for row in summary if row.open_session)
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
                w.writerow(
                    [
                        row.user,
                        len(row.events["fetch"]),
                        len(row.events["submit"]),
                        len(row.events["save"]),
                        len(row.sessions),
                        row.first_fetch.isoformat() if row.first_fetch else "",
                        row.last_submit.isoformat() if row.last_submit else "",
                        row.last_save.isoformat() if row.last_save else "",
                        fmt_delta(row.total) if row.total else "",
                        fmt_delta(row.sess_total) if row.sessions else "",
                        "yes" if row.open_session else "",
                        "yes" if row.last_submit else "NO",
                    ]
                )
        print(f"Summary CSV written to {args.csv}")


def fetch_to_submit(summary: list[StudentSummary], show: bool = True):
    # ---- 4. fetch -> submit durations ------------------------------------------
    if not show:
        return
    print("=" * 78)
    print("FETCH -> SUBMIT DURATIONS (each submit paired with the latest prior fetch)")
    print("=" * 78)
    for row in summary:
        fetches = sorted(row.events["fetch"])
        submits = sorted(row.events["submit"])
        if not submits:
            print(
                hl(
                    f"{row.user:<15}  fetched {len(fetches)}x, never submitted",
                    Colours.RED,
                )
            )
            continue
        for sub in submits:
            prior = [f for f in fetches if f <= sub]
            if prior:
                f = prior[-1]
                print(
                    f"{row.user:<15}  {f:%m-%d %H:%M:%S} -> {sub:%m-%d %H:%M:%S}"
                    f"  = {fmt_delta(sub - f)}"
                )
            else:
                print(
                    hl(
                        f"{row.user:<15}  {sub:%m-%d %H:%M:%S}  "
                        f"submit WITHOUT prior fetch",
                        Colours.RED,
                    )
                )
    print()


def session_durations(summary: list[StudentSummary], show: bool = True):
    # ---- 3. session durations --------------------------------------------------
    if not show:
        return
    print("=" * 78)
    print("SESSIONS (start marker -> signal 15)")
    print("=" * 78)
    for row in summary:
        for sess in row.sessions:
            if sess.stop:
                print(
                    f"{row.user:<15}  {sess.start:%m-%d %H:%M:%S} -> "
                    f"{sess.stop:%m-%d %H:%M:%S}  = {fmt_delta(sess.stop - sess.start)}"
                )
            else:
                print(
                    hl(
                        f"{row.user:<15}  {sess.start:%m-%d %H:%M:%S} -> still running / no stop event"
                    )
                )
    print()


def per_student(
    per_user, show: bool = True, unsubmitted_only: bool = False
) -> list[StudentSummary]:
    # ---- 2. per-student summary ----------------------------------------------
    summary: list[StudentSummary] = []
    for u, ev in per_user.items():
        ff = min(ev["fetch"]) if ev["fetch"] else None
        ls = max(ev["submit"]) if ev["submit"] else None
        last_save = max(ev["save"]) if ev["save"] else None
        total = ls - ff if ff and ls else None
        sessions = pair_sessions(ev["start"], ev["stop"])
        sess_total = sum((sp - st for st, sp in sessions if sp), timedelta())
        open_sess = any(sp is None for st, sp in sessions)
        summary.append(
            StudentSummary(
                sort_key=ff or ls or datetime.max,
                user=u,
                events=ev,
                first_fetch=ff,
                last_submit=ls,
                total=total,
                sessions=sessions,
                sess_total=sess_total,
                open_session=open_sess,
                last_save=last_save,
            )
        )
    summary.sort(key=lambda r: (r.sort_key, r.user))

    if show:
        print("=" * 78)
        print("PER-STUDENT SUMMARY (first fetch -> last submit, saves, session time)")
        print("=" * 78)
        header = (
            f"{'username':<15}  {'fetch':>6}  {'submit':>7}  {'save':>6}  "
            f"{'sess':>5}  {'sess start':<17}  {'first fetch':<12}  "
            f"{'last submit':<12}  {'last save':<12}  {'total':>12}  {'in sess':>12}"
        )
        print(header)
        print("-" * len(header))
        for row in summary:
            if unsubmitted_only and row.last_submit:
                continue
            # Year is shown only in the first date column (sess start).
            first_sess = min((s.start for s in row.sessions), default=None)
            fs_s = f"{first_sess:%Y-%m-%d %H:%M}" if first_sess else "-"
            ff_s = f"{row.first_fetch:%m-%d %H:%M}" if row.first_fetch else "-"
            ls_s = f"{row.last_submit:%m-%d %H:%M}" if row.last_submit else "NEVER"
            save_s = f"{row.last_save:%m-%d %H:%M}" if row.last_save else "-"
            sess_s = fmt_delta(row.sess_total) if row.sessions else "-"
            if row.open_session:
                sess_s += "+"
            line = (
                f"{row.user:<15}  {len(row.events['fetch']):>6}"
                f"  {len(row.events['submit']):>7}  {len(row.events['save']):>6}"
                f"  {len(row.sessions):>5}  "
                f"{fs_s:<17}  {ff_s:<12}  {ls_s:<12}  {save_s:<12}"
                f"  {fmt_delta(row.total):>12}  {sess_s:>12}"
            )
            print(hl(line, Colours.RED) if not row.last_submit else line)
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
    print(hl(f"FETCHED BUT NEVER SUBMITTED: {len(missing)} student(s)", Colours.RED))
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
