#!/usr/bin/env python3
"""Generate deterministic per-student randomized nbgrader notebooks.

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


def _load_students(args: argparse.Namespace) -> list[str]:
    students: set[str] = set()
    if args.students:
        students.update(x.strip() for x in args.students.split(",") if x.strip())
    if args.students_file:
        for line in Path(args.students_file).read_text(encoding="utf-8").splitlines():
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
    k: int,
    rng: random.Random,
) -> list[str]:
    if k > len(population):
        raise ValueError(
            f"pick_count={k} is larger than question count={len(population)}"
        )

    chosen: list[str] = []
    items = list(zip(population, weights))
    for _ in range(k):
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
    base_notebook: dict[str, Any],
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

    notebook = dict(base_notebook)
    notebook["cells"] = generated_cells
    metadata = dict(base_notebook.get("metadata") or {})
    metadata["aalto_nbgrader_randomization"] = {
        "student": student,
        "seed": seed_value,
        "selected_question_ids": sorted(selected_ids),
        "generated_unix_time": int(time.time()),
    }
    notebook["metadata"] = metadata
    return notebook


def _manifest_path(output_dir: Path, assignment: str) -> Path:
    return output_dir / assignment / "_randomization_manifest.json"


def _acquire_lock(lock_path: Path, timeout_s: int) -> int:
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return fd
        except FileExistsError:
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Timed out waiting for lock {lock_path}")
            time.sleep(1)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    args = parse_args()
    students = _load_students(args)
    if not students:
        print("No students provided; nothing to generate.", file=sys.stderr)
        return 2

    if args.pick_count <= 0:
        raise ValueError("pick_count must be > 0")

    source_path = Path(args.source_notebook)
    output_dir = Path(args.output_dir)
    assignment_dir = output_dir / args.assignment
    assignment_dir.mkdir(parents=True, exist_ok=True)
    lock_path = assignment_dir / ".randomization.lock"

    _acquire_lock(lock_path, timeout_s=args.lock_timeout)
    try:
        source_text = source_path.read_text(encoding="utf-8")
        source_hash = _source_digest(source_text)
        source_notebook = json.loads(source_text)

        common_cells, question_cells, question_weights, question_order = extract_bank(
            source_notebook,
            question_metadata_key=args.question_metadata_key,
            weight_key=args.weight_key,
        )
        question_ids = list(question_cells.keys())
        weights = [question_weights[qid] for qid in question_ids]

        manifest_path = _manifest_path(output_dir, args.assignment)
        previous_manifest = None
        if manifest_path.exists():
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        desired_manifest_header = {
            "course_slug": args.course_slug,
            "assignment": args.assignment,
            "source_notebook": str(source_path),
            "source_hash": source_hash,
            "pick_count": args.pick_count,
            "question_metadata_key": args.question_metadata_key,
            "weight_key": args.weight_key,
            "question_ids": sorted(question_ids),
            "students": students,
        }
        if (
            previous_manifest
            and previous_manifest.get("config") == desired_manifest_header
            and not args.force
        ):
            print(f"Randomization already up to date for {args.assignment}.")
            return 0

        manifest: dict[str, Any] = {
            "config": desired_manifest_header,
            "generated_at": int(time.time()),
            "per_student": {},
        }

        for student in students:
            seed_value = _seed(
                seed_salt=args.seed_salt,
                course_slug=args.course_slug,
                assignment=args.assignment,
                student=student,
            )
            rng = random.Random(seed_value)
            selected = weighted_without_replacement(
                population=question_ids,
                weights=weights,
                k=args.pick_count,
                rng=rng,
            )
            selected_set = set(selected)
            generated_notebook = build_notebook(
                base_notebook=source_notebook,
                common_cells=common_cells,
                question_cells=question_cells,
                selected_ids=selected_set,
                question_order=question_order,
                student=student,
                seed_value=seed_value,
            )
            output_path = (
                output_dir
                / args.assignment
                / "students"
                / student
                / f"{args.assignment}.ipynb"
            )
            _write_json(output_path, generated_notebook)

            manifest["per_student"][student] = {
                "seed": seed_value,
                "selected_question_ids": selected,
                "path": str(output_path),
            }

        _write_json(manifest_path, manifest)
        print(
            f"Generated randomized notebooks for {len(students)} students in {output_dir}/{args.assignment}"
        )
        return 0
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
