#!/usr/bin/env python3
"""Custom nbgrader release plugin for per-student randomized assignments.

This plugin keeps the normal nbgrader exchange flow and only alters release:
1. If randomisation is not enabled for the assignment, perform the standard
   release to exchange outbound.
2. If randomisation is enabled for the assignment, generate one
   student-specific notebook per student with only the selected questions, and
   place them in a per-user directory for the assignment, so that they can be
   mounted in the user's single-user container and fetched as normal.

This tool reads one source notebook containing a question bank and writes one
student-specific notebook per student with only the selected questions.

Question-bank cell format:
- A cell belongs to a randomizable question when cell metadata contains
  `question_metadata_key` (default: "aalto_nbgrader_bank") with a dict:

    {
      "question_id": "q1",
      "weight": 1.0
    }

- Cells without that metadata are treated as common cells and included for all
  generated student notebooks.

The generated notebooks keep original cell metadata (including nbgrader
metadata), allowing standard nbgrader autograding once they are released and
submitted through the usual pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

from nbgrader.exchange.default.release_assignment import ExchangeReleaseAssignment
from traitlets.traitlets import Bool, Int, Unicode


class RandomizedExchangeReleaseAssignment(ExchangeReleaseAssignment):
    """Release plugin that generates randomized notebook variants per student."""

    randomization_enabled = Bool(
        False,
        help="Enable randomized notebook generation on release.",
    ).tag(config=True)

    randomization_root = Unicode(
        "",
        help=(
            "Root directory containing randomized assignment outputs, for example "
            "'/courses/<slug>/files/randomized'."
        ),
    ).tag(config=True)

    source_notebook = Unicode(
        "",
        help=(
            "Path to source bank notebook. If empty, defaults to "
            "'<release source path>/<assignment_id>.ipynb'."
        ),
    ).tag(config=True)

    pick_count = Int(
        0,
        help="Number of randomizable questions selected per student.",
    ).tag(config=True)

    students = Unicode(
        "",
        help="Comma-separated student usernames.",
    ).tag(config=True)

    students_file = Unicode(
        "",
        help="Path to newline-separated student usernames.",
    ).tag(config=True)

    seed_salt = Unicode(
        "",
        help="Optional extra salt used in deterministic per-student seeding.",
    ).tag(config=True)

    question_metadata_key = Unicode(
        "aalto_nbgrader_bank",
        help="Cell metadata key containing randomization metadata.",
    ).tag(config=True)

    weight_key = Unicode(
        "weight",
        help="Weight key inside question metadata.",
    ).tag(config=True)

    force = Bool(
        False,
        help="Regenerate variants even if manifest config matches existing output.",
    ).tag(config=True)

    lock_timeout = Int(
        90,
        help="Lock wait timeout in seconds.",
    ).tag(config=True)

    def _source_notebook_path(self, assignment: str) -> Path:
        if self.source_notebook:
            return Path(self.source_notebook)

        src_path = getattr(self, "src_path", "")
        if not isinstance(src_path, str) or not src_path:
            raise ValueError(
                "source_notebook was not configured and release source path is unavailable"
            )
        return Path(src_path) / f"{assignment}.ipynb"

    def copy_files(self):
        if not self.randomization_enabled:
            self.log.info(
                "Randomization disabled; skipping variant generation and copying files normally"
            )
            super().copy_files()
            return

        self.log.info("Randomization enabled; generating per-student variants")

        if not self.randomization_root:
            raise ValueError(
                "RandomizedExchangeReleaseAssignment.randomization_root must be set"
            )
        if self.pick_count <= 0:
            raise ValueError(
                "RandomizedExchangeReleaseAssignment.pick_count must be > 0"
            )

        students = _load_students_from_values(self.students, self.students_file)
        if not students:
            raise ValueError(
                "No students configured. Set RandomizedExchangeReleaseAssignment.students "
                "or RandomizedExchangeReleaseAssignment.students_file"
            )

        # Ignore the assignment file in coursedir.ignore, since we are generating it ourselves.
        self.coursedir.ignore.append(f"{self.coursedir.assignment_id}.ipynb")
        self.log.info("ignored files in coursedir.ignore: %s", self.coursedir.ignore)

        # Run standard release workflow first.
        super().copy_files()

        assignment = self.coursedir.assignment_id
        source_path = self._source_notebook_path(assignment)

        _generate_randomized_notebooks(
            course_slug=self.coursedir.course_id,
            assignment=assignment,
            source_path=source_path,
            output_dir=Path(self.randomization_root),
            pick_count=self.pick_count,
            students=students,
            seed_salt=self.seed_salt,
            question_metadata_key=self.question_metadata_key,
            weight_key=self.weight_key,
            force=self.force,
            lock_timeout=self.lock_timeout,
            logger=self.log,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-slug", required=True)
    parser.add_argument("--assignment", required=True)
    parser.add_argument("--source-notebook", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--pick-count", type=int, required=True)
    parser.add_argument("--students", default="")
    parser.add_argument("--students-file")
    parser.add_argument("--seed-salt", default="")
    parser.add_argument("--question-metadata-key", default="aalto_nbgrader_bank")
    parser.add_argument("--weight-key", default="weight")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--lock-timeout", type=int, default=90)
    return parser.parse_args()


def _load_students_from_values(students_csv: str, students_file: str) -> list[str]:
    students: set[str] = set()
    if students_csv:
        students.update(x.strip() for x in students_csv.split(",") if x.strip())
    if students_file:
        for line in Path(students_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                students.add(line)
    return sorted(students)


def _source_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _seed(seed_salt: str, course_slug: str, assignment: str, student: str) -> int:
    raw = f"{seed_salt}|{course_slug}|{assignment}|{student}"
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], 16)


def weighted_without_replacement(
    population: list[str],
    weights: list[float],
    pick_count: int,
    rng: random.Random,
) -> list[str]:
    if pick_count > len(population):
        raise ValueError(
            f"pick_count={pick_count} is larger than question count={len(population)}"
        )

    chosen: list[str] = []
    items = list(zip(population, weights))
    for _ in range(pick_count):
        total = sum(weight for _, weight in items)
        if total <= 0:
            raise ValueError("All remaining question weights are <= 0")
        r = rng.random() * total
        acc = 0.0
        idx = -1
        for i, (_, w) in enumerate(items):
            acc += w
            if acc >= r:
                idx = i
                break
        if idx == -1:
            idx = len(items) - 1
        qid, _ = items.pop(idx)
        chosen.append(qid)
    return chosen


def extract_bank(
    notebook: dict[str, Any],
    question_metadata_key: str,
    weight_key: str,
) -> tuple[
    list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, float], list[str]
]:
    common_cells: list[dict[str, Any]] = []
    question_cells: dict[str, list[dict[str, Any]]] = {}
    question_weights: dict[str, float] = {}
    first_order: list[str] = []

    for cell in notebook.get("cells", []):
        meta = cell.get("metadata") or {}
        bank_meta = meta.get(question_metadata_key)
        if not isinstance(bank_meta, dict):
            common_cells.append(cell)
            continue

        question_id = bank_meta.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(
                f"Question cell has invalid {question_metadata_key}.question_id: {bank_meta!r}"
            )

        if question_id not in question_cells:
            question_cells[question_id] = []
            first_order.append(question_id)
        question_cells[question_id].append(cell)

        if question_id not in question_weights:
            weight = bank_meta.get(weight_key, 1.0)
            if not isinstance(weight, (int, float)):
                raise ValueError(
                    f"Question {question_id} has non-numeric weight {weight!r}"
                )
            if weight <= 0:
                raise ValueError(f"Question {question_id} has non-positive weight")
            question_weights[question_id] = float(weight)

    if not question_cells:
        raise ValueError(
            f"No randomizable questions found. Add cell metadata key {question_metadata_key}."
        )

    return common_cells, question_cells, question_weights, first_order


def build_notebook(
    source_notebook: dict[str, Any],
    common_cells: list[dict[str, Any]],
    question_cells: dict[str, list[dict[str, Any]]],
    selected_ids: set[str],
    question_order: list[str],
    student: str,
    seed_value: int,
) -> dict[str, Any]:
    generated_cells: list[dict[str, Any]] = []
    generated_cells.extend(common_cells)
    for qid in question_order:
        if qid in selected_ids:
            generated_cells.extend(question_cells[qid])

    notebook = dict(source_notebook)
    notebook["cells"] = generated_cells
    metadata = dict(source_notebook.get("metadata") or {})
    metadata["aalto_nbgrader_randomization"] = {
        "student": student,
        "seed": seed_value,
        "selected_question_ids": sorted(selected_ids),
        "generated_unix_time": int(time.time()),
    }
    notebook["metadata"] = metadata
    return notebook


def _acquire_lock(lock_path: Path, timeout_s: int) -> None:
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return
        except FileExistsError:
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Timed out waiting for lock {lock_path}")
            time.sleep(1)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _generate_randomized_notebooks(
    *,
    course_slug: str,
    assignment: str,
    source_path: Path,
    output_dir: Path,
    pick_count: int,
    students: list[str],
    seed_salt: str,
    question_metadata_key: str,
    weight_key: str,
    force: bool,
    lock_timeout: int,
    logger: Any | None,
) -> None:
    if pick_count <= 0:
        raise ValueError("pick_count must be > 0")
    if not students:
        raise ValueError("No students provided; nothing to generate")

    assignment_dir = output_dir / assignment
    assignment_dir.mkdir(parents=True, exist_ok=True)
    lock_path = assignment_dir / ".randomization.lock"

    _acquire_lock(lock_path, timeout_s=lock_timeout)
    try:
        source_text = source_path.read_text(encoding="utf-8")
        source_hash = _source_digest(source_text)
        source_notebook = json.loads(source_text)

        common_cells, question_cells, question_weights, question_order = extract_bank(
            source_notebook,
            question_metadata_key,
            weight_key,
        )
        question_ids = list(question_cells.keys())
        weights = [question_weights[qid] for qid in question_ids]

        manifest_path = output_dir / assignment / "_randomization_manifest.json"
        previous_manifest = None
        if manifest_path.exists():
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        desired_manifest_header = {
            "course_slug": course_slug,
            "assignment": assignment,
            "source_notebook": str(source_path),
            "source_hash": source_hash,
            "pick_count": pick_count,
            "question_metadata_key": question_metadata_key,
            "weight_key": weight_key,
            "question_ids": sorted(question_ids),
            "students": students,
        }
        if (
            previous_manifest
            and previous_manifest.get("config") == desired_manifest_header
            and not force
        ):
            if logger is None:
                print(f"Randomization already up to date for {assignment}.")
            else:
                logger.info("Randomization already up to date for %s", assignment)
            return

        manifest: dict[str, Any] = {
            "config": desired_manifest_header,
            "generated_at": int(time.time()),
            "per_student": {},
        }

        for student in students:
            seed_value = _seed(seed_salt, course_slug, assignment, student)
            rng = random.Random(seed_value)
            selected = weighted_without_replacement(
                question_ids, weights, pick_count, rng
            )
            selected_ids = set(selected)
            generated_notebook = build_notebook(
                source_notebook,
                common_cells,
                question_cells,
                selected_ids,
                question_order,
                student,
                seed_value,
            )
            output_path = (
                output_dir / assignment / "students" / student / f"{assignment}.ipynb"
            )
            _write_json(output_path, generated_notebook)

            manifest["per_student"][student] = {
                "seed": seed_value,
                "selected_question_ids": selected,
                "path": str(output_path),
            }

        _write_json(manifest_path, manifest)

        if logger is None:
            print(
                f"Generated randomized notebooks for {len(students)} students "
                f"in {output_dir}/{assignment}"
            )
        else:
            logger.info(
                "Generated randomized notebooks for %d students in %s/%s",
                len(students),
                output_dir,
                assignment,
            )
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    args = parse_args()
    students = _load_students_from_values(args.students, args.students_file)
    if not students:
        print("No students provided; nothing to generate.", file=sys.stderr)
        return 2

    if args.pick_count <= 0:
        raise ValueError("pick_count must be > 0")

    _generate_randomized_notebooks(
        course_slug=args.course_slug,
        assignment=args.assignment,
        source_path=Path(args.source_notebook),
        output_dir=Path(args.output_dir),
        pick_count=args.pick_count,
        students=students,
        seed_salt=args.seed_salt,
        question_metadata_key=args.question_metadata_key,
        weight_key=args.weight_key,
        force=args.force,
        lock_timeout=args.lock_timeout,
        logger=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
