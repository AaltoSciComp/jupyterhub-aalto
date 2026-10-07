#!/usr/bin/env python3
"""Custom nbgrader release plugin for per-student randomised assignments.

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
- A cell belongs to a randomisable question when cell metadata contains
  `question_metadata_key` (default: "aalto_nbgrader_bank") with a dict:

    {
      "question_id": "q1",
      "weight": 1.0,
      "topic": "easy",
      "subtopics": ["validation", "leak_check"]
    }

  `weight` defaults to 1.0. `subtopics` (optional, outermost first) places
  the question in a tree of subtopic groups below its `topic` (optional);
  see "Sampling" below.

- Cells without that metadata are treated as common cells and included for all
  generated student notebooks.

Notebook-level settings, read from the notebook metadata under the same key
(both optional):

    {"pick_count": 3, "one_question_per_subtopic": true}

- `pick_count`: questions per student. The `pick_count` trait overrides it
  when set (> 0).
- `one_question_per_subtopic`: see "Sampling".

Sampling:
- Without `one_question_per_subtopic`, `pick_count` questions are drawn by
  weight, without replacement, from all questions.
- With it, a student never gets two questions from the same subtopic group,
  at any level of the tree. The draw picks `pick_count` units among the
  top-level units -- each question without subtopics, and each outermost
  subtopic group -- and then one question inside every picked group, again
  by weight, level by level. A group's weight is the mean of its units'
  weights, so a group of variants is drawn as often as a single question.
  Groups are keyed by topic and subtopic together, so the same subtopic
  name in two topics is two groups.
- There are no per-topic quotas: questions of different topics share one
  pool, so if their points differ, so do the students' totals.
- Don't switch plugin versions during a running exam: the first release
  with another version re-draws every student.

Question files:
- Files under `<question_files_directory>/<question_id>/` (default
  "sources/<question_id>/") belong to that question. That directory is left
  out of the normal release copy, and each student's directory receives only
  the folders of their selected questions, so a student never gets the files
  of questions they weren't given. `question_files_directory` must be a
  single directory name at the top of the release folder; set it to "" to
  release every file normally.

The generated notebooks keep original cell metadata (including nbgrader
metadata), allowing standard nbgrader autograding once they are released and
submitted through the usual pipeline.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import time
from pathlib import Path
from stat import (
    S_IRGRP,
    S_ISGID,
    S_IWGRP,
)
from typing import Any, List, Optional, Tuple

from nbgrader.exchange.default.release_assignment import ExchangeReleaseAssignment
from traitlets.traitlets import Bool, Int, Unicode


class RandomisedExchangeReleaseAssignment(ExchangeReleaseAssignment):
    """Release plugin that generates randomised notebook variants per student."""

    randomisation_enabled = Bool(
        False,
        help="Enable randomised notebook generation on release.",
    ).tag(config=True)

    randomisation_root = Unicode(
        "",
        help=(
            "Root directory containing randomised assignment outputs, for example "
            "'/courses/<slug>/files/randomised'."
        ),
    ).tag(config=True)

    pick_count = Int(
        0,
        help=(
            "Number of randomisable questions selected per student. 0 reads "
            "`pick_count` from the notebook metadata instead."
        ),
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
        help="Cell and notebook metadata key containing randomisation metadata.",
    ).tag(config=True)

    weight_key = Unicode(
        "weight",
        help="Weight key inside question metadata.",
    ).tag(config=True)

    subtopics_key = Unicode(
        "subtopics",
        help="Key inside question metadata listing its subtopic groups, outermost first.",
    ).tag(config=True)

    topic_key = Unicode(
        "topic",
        help=(
            "Key inside question metadata naming the question's topic; subtopic groups "
            "of the same name in different topics are kept apart."
        ),
    ).tag(config=True)

    question_files_directory = Unicode(
        "sources",
        help=(
            "Directory in the release folder with one subfolder per question_id. It is "
            "left out of the normal release copy; each student gets only the subfolders "
            "of their selected questions. Empty releases every file normally."
        ),
    ).tag(config=True)

    force = Bool(
        False,
        help="Regenerate variants even if manifest config matches existing output.",
    ).tag(config=True)

    lock_timeout = Int(
        90,
        help="Lock wait timeout in seconds.",
    ).tag(config=True)

    def copy_files(self):
        if not self.randomisation_enabled:
            self.log.info(
                "Randomisation disabled; skipping variant generation and copying files normally"
            )
            super().copy_files()
            return

        self.log.info("Randomisation enabled; generating per-student variants")

        if not self.randomisation_root:
            raise ValueError(
                "RandomisedExchangeReleaseAssignment.randomisation_root must be set"
            )
        if self.pick_count < 0:
            raise ValueError(
                "RandomisedExchangeReleaseAssignment.pick_count must be >= 0"
            )

        students = _load_students_from_values(self.students, self.students_file)
        if not students:
            raise ValueError(
                "No students configured. Set RandomisedExchangeReleaseAssignment.students "
                "or RandomisedExchangeReleaseAssignment.students_file"
            )

        name = self.question_files_directory
        if name and (
            Path(name).name != name
            or name in (".", "..")
            or any(c in name for c in "*?[]")
        ):
            raise ValueError(
                "RandomisedExchangeReleaseAssignment.question_files_directory must be a "
                f"single directory name, not a path: {self.question_files_directory!r}"
            )

        # Ignore the assignment file, since we are generating it ourselves, and the
        # question files, which only go to the students who get those questions.
        # nbgrader matches these patterns against file and directory names at every
        # level of the tree. coursedir is shared with every later step of a
        # long-running formgrader (collect, autograde, ...), so the extra patterns
        # apply to this copy only.
        # Check the bank notebook before the release copy, which replaces outbound.
        source_path = Path(self.src_path) / f"{self.coursedir.assignment_id}.ipynb"
        if not source_path.is_file():
            found = sorted(p.name for p in Path(self.src_path).glob("*.ipynb"))
            raise FileNotFoundError(
                f"Randomisation needs the bank notebook {source_path}, named after the "
                f"assignment; the release folder has {found or 'no notebooks'}. Run "
                f"`nbgrader generate_assignment {self.coursedir.assignment_id}` with the "
                f"notebook saved as {source_path.name} in the source folder."
            )

        self.log.info(
            f"{self.root=}, {self.coursedir.course_id=}, {self.coursedir.assignment_id=}"
        )
        # Run standard release workflow first.
        self.log.info(
            f"Copying files normally to {self.dest_path} before generating randomised variants"
        )
        original_ignore = list(self.coursedir.ignore)
        self.coursedir.ignore = original_ignore + [
            f"{self.coursedir.assignment_id}.ipynb",
            *([self.question_files_directory] if self.question_files_directory else []),
        ]
        try:
            self.log.info(
                "ignored files in coursedir.ignore: %s", self.coursedir.ignore
            )
            super().copy_files()
        finally:
            self.coursedir.ignore = original_ignore

        assignment = self.coursedir.assignment_id
        question_files_root = (
            Path(self.src_path) / self.question_files_directory
            if self.question_files_directory
            else None
        )

        _generate_randomised_notebooks(
            course_slug=self.coursedir.course_id,
            assignment=assignment,
            source_path=source_path,
            output_dir=Path(self.randomisation_root),
            pick_count_override=self.pick_count,
            students=students,
            seed_salt=self.seed_salt,
            question_metadata_key=self.question_metadata_key,
            weight_key=self.weight_key,
            subtopics_key=self.subtopics_key,
            topic_key=self.topic_key,
            question_files_root=question_files_root,
            force=self.force,
            lock_timeout=self.lock_timeout,
            groupshared=self.coursedir.groupshared,
            logger=self.log,
        )


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


def _tree_digest(root: Path | None) -> str:
    """Hash every file's relative path and bytes under `root` ("" when there is none)."""
    if root is None or not root.is_dir():
        return ""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


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

    if len(weights) != len(population):
        raise ValueError(
            f"weights length {len(weights)} does not match population length {len(population)}"
        )

    if pick_count <= 0:
        raise ValueError(f"pick_count={pick_count} must be > 0")

    if any(weight <= 0 for weight in weights):
        raise ValueError("One or more question weights are <= 0")

    if pick_count == len(population):
        return list(population)

    chosen: list[str] = []
    items = list(zip(population, weights))
    total = sum(weight for _, weight in items)
    for _ in range(pick_count):
        if total <= 0:
            raise ValueError("All remaining question weights are <= 0")
        r = rng.random() * total
        acc = 0.0
        idx = -1
        for i, (_, weight) in enumerate(items):
            acc += weight
            if acc >= r:
                idx = i
                break
        if idx == -1:
            idx = len(items) - 1
        chosen_id, chosen_weight = items.pop(idx)
        chosen.append(chosen_id)
        total -= chosen_weight
    return chosen


# A question as the draw sees it: (question_id, weight, subtopics outermost first).
# typing's Tuple/List keep these runtime aliases working on Python 3.8.
_Member = Tuple[str, float, Tuple[str, ...]]
# One sampling unit at some depth of the subtopic tree: a question, or a subtopic
# group holding the questions below it. (label, weight, question_id or None for a
# group, the group's members or None for a question).
_Unit = Tuple[str, float, Optional[str], Optional[List[_Member]]]


def _units(members: list[_Member], depth: int) -> list[_Unit]:
    """Split `members` (question_id, weight, subtopics) into the units at `depth`."""
    groups: dict[str, list[_Member]] = {}
    units: list[_Unit] = []
    for member in members:
        qid, weight, subtopics = member
        if len(subtopics) > depth:
            name = subtopics[depth]
            if name not in groups:
                groups[name] = []
                # The group's weight is filled in once all its members are known.
                units.append((f"subtopic:{name}", 0.0, None, groups[name]))
            groups[name].append(member)
        else:
            units.append((f"question:{qid}", weight, qid, None))
    return [
        (label, weight, qid, None)
        if sub is None
        else (label, _group_weight(sub, depth + 1), None, sub)
        for label, weight, qid, sub in units
    ]


def _group_weight(members: list[_Member], depth: int) -> float:
    """A group is as likely as one of its units: the mean of their weights."""
    units = _units(members, depth)
    return sum(weight for _, weight, _, _ in units) / len(units)


def _draw_from_units(
    units: list[_Unit], pick_count: int, depth: int, rng: random.Random
) -> list[str]:
    labels = [label for label, _, _, _ in units]
    weights = [weight for _, weight, _, _ in units]
    by_label = {unit[0]: unit for unit in units}
    chosen: list[str] = []
    for label in weighted_without_replacement(labels, weights, pick_count, rng):
        _, _, qid, members = by_label[label]
        if qid is not None:
            chosen.append(qid)
        else:
            assert members is not None
            chosen.extend(
                _draw_from_units(_units(members, depth + 1), 1, depth + 1, rng)
            )
    return chosen


def draw_questions(
    question_ids: list[str],
    weights: list[float],
    subtopics: dict[str, tuple[str, ...]],
    pick_count: int,
    rng: random.Random,
    one_question_per_subtopic: bool,
) -> list[str]:
    """Draw `pick_count` question ids; see "Sampling" in the module docstring."""
    if not one_question_per_subtopic:
        return weighted_without_replacement(question_ids, weights, pick_count, rng)
    if any(weight <= 0 for weight in weights):
        raise ValueError("One or more question weights are <= 0")
    members = [
        (qid, w, subtopics.get(qid, ())) for qid, w in zip(question_ids, weights)
    ]
    units = _units(members, 0)
    if pick_count > len(units):
        raise ValueError(
            f"pick_count={pick_count} is larger than the {len(units)} independent units "
            "(questions without subtopics, plus top-level subtopic groups) the bank has "
            "with one_question_per_subtopic"
        )
    return _draw_from_units(units, pick_count, 0, rng)


def extract_bank(
    notebook: dict[str, Any],
    question_metadata_key: str,
    weight_key: str,
    subtopics_key: str = "subtopics",
    topic_key: str = "topic",
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, float],
    list[str],
    dict[str, tuple[str, ...]],
]:
    common_cells: list[dict[str, Any]] = []
    question_cells: dict[str, list[dict[str, Any]]] = {}
    question_weights: dict[str, float] = {}
    question_subtopics: dict[str, tuple[str, ...]] = {}
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

            subtopics = bank_meta.get(subtopics_key, [])
            if not isinstance(subtopics, list) or not all(
                isinstance(name, str) and name for name in subtopics
            ):
                raise ValueError(
                    f"Question {question_id} has invalid {subtopics_key}: {subtopics!r}"
                )
            # Subtopics are folders below the question's topic, so the same name in
            # two topics is two different groups: the top level is keyed by both.
            topic = bank_meta.get(topic_key)
            if subtopics and isinstance(topic, str) and topic:
                subtopics = [f"{topic}/{subtopics[0]}", *subtopics[1:]]
            question_subtopics[question_id] = tuple(subtopics)

    if not question_cells:
        raise ValueError(
            f"No randomisable questions found. Add cell metadata key {question_metadata_key}."
        )

    return (
        common_cells,
        question_cells,
        question_weights,
        first_order,
        question_subtopics,
    )


def sampling_settings(
    notebook: dict[str, Any], question_metadata_key: str, pick_count_override: int
) -> tuple[int, bool]:
    """Return `(pick_count, one_question_per_subtopic)` from the notebook metadata.

    A `pick_count_override` > 0 (the trait) wins over the notebook's own value.
    """
    settings = (notebook.get("metadata") or {}).get(question_metadata_key) or {}
    if not isinstance(settings, dict):
        raise TypeError(f"Notebook metadata {question_metadata_key} must be a dict")
    pick_count = pick_count_override or settings.get("pick_count", 0)
    if (
        not isinstance(pick_count, int)
        or isinstance(pick_count, bool)
        or pick_count <= 0
    ):
        raise TypeError(
            "pick_count must be a positive integer: set "
            "RandomisedExchangeReleaseAssignment.pick_count, or pick_count in the "
            f"notebook metadata under {question_metadata_key} (got {pick_count!r})"
        )
    one_per_subtopic = settings.get("one_question_per_subtopic", False)
    if not isinstance(one_per_subtopic, bool):
        raise TypeError(
            f"one_question_per_subtopic must be true or false (got {one_per_subtopic!r})"
        )
    return pick_count, one_per_subtopic


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
    metadata["aalto_nbgrader_randomisation"] = {
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


def _mkdir_with_mode(path: Path, mode: int) -> None:
    missing: list[Path] = []
    directory = path
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent

    for directory in reversed(missing):
        try:
            directory.mkdir(mode=mode)
        except FileExistsError:
            if not directory.is_dir():
                raise
        else:
            os.chmod(directory, mode | directory.stat().st_mode)


def _write_json(path: Path, data: Any, *, file_mode: int, dir_mode: int) -> None:
    _mkdir_with_mode(path.parent, dir_mode)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, file_mode)
    tmp.replace(path)


def _copy_question_files(
    question_files_root: Path,
    selected: list[str],
    dest_root: Path,
    *,
    file_mode: int,
    dir_mode: int,
) -> None:
    """Copy each selected question's folder from `question_files_root` into `dest_root`.

    `dest_root` is emptied first, so a regenerated draw never keeps the files of
    questions the student no longer has. A question without a folder has no files.
    """
    if dest_root.exists():
        shutil.rmtree(dest_root)
    for qid in selected:
        source = question_files_root / qid
        if not source.is_dir():
            continue
        _mkdir_with_mode(dest_root, dir_mode)
        shutil.copytree(source, dest_root / qid)
        for directory, _, files in os.walk(dest_root / qid):
            os.chmod(directory, dir_mode)
            for name in files:
                os.chmod(Path(directory) / name, file_mode)


def _generate_randomised_notebooks(
    *,
    course_slug: str,
    assignment: str,
    source_path: Path,
    output_dir: Path,
    pick_count_override: int,
    students: list[str],
    seed_salt: str,
    question_metadata_key: str,
    weight_key: str,
    subtopics_key: str,
    topic_key: str,
    question_files_root: Path | None,
    force: bool,
    lock_timeout: int,
    groupshared: bool,
    logger: Any | None,
) -> None:
    if not students:
        raise ValueError("No students provided; nothing to generate")

    manifest_dir = output_dir / "manifests" / assignment
    _mkdir_with_mode(manifest_dir, 0o770)
    lock_path = manifest_dir / ".randomisation.lock"

    if logger is None:
        print(
            f"Generating randomised notebooks for assignment {assignment} in {output_dir}"
        )
    else:
        logger.info(
            "Generating randomised notebooks for assignment %s in %s",
            assignment,
            output_dir,
        )

    _acquire_lock(lock_path, timeout_s=lock_timeout)
    try:
        source_text = source_path.read_text(encoding="utf-8")
        source_hash = _source_digest(source_text)
        source_notebook = json.loads(source_text)

        common_cells, question_cells, question_weights, question_order, subtopics = (
            extract_bank(
                source_notebook,
                question_metadata_key,
                weight_key,
                subtopics_key,
                topic_key,
            )
        )
        pick_count, one_per_subtopic = sampling_settings(
            source_notebook, question_metadata_key, pick_count_override
        )
        question_ids = list(question_cells.keys())
        weights = [question_weights[qid] for qid in question_ids]

        manifest_file_path = manifest_dir / "_randomisation_manifest.json"
        previous_manifest = None
        if manifest_file_path.exists():
            previous_manifest = json.loads(
                manifest_file_path.read_text(encoding="utf-8")
            )

        desired_manifest_header = {
            "course_slug": course_slug,
            "assignment": assignment,
            "source_notebook": str(source_path),
            "source_hash": source_hash,
            "question_files": str(question_files_root or ""),
            "question_files_hash": _tree_digest(question_files_root),
            "pick_count": pick_count,
            "one_question_per_subtopic": one_per_subtopic,
            "question_metadata_key": question_metadata_key,
            "weight_key": weight_key,
            "subtopics_key": subtopics_key,
            "topic_key": topic_key,
            "question_ids": sorted(question_ids),
            "students": students,
        }
        if (
            previous_manifest
            and previous_manifest.get("config") == desired_manifest_header
            and not force
        ):
            if logger is None:
                print(f"Randomisation already up to date for {assignment}.")
            else:
                logger.info("Randomisation already up to date for %s", assignment)
            return

        manifest: dict[str, Any] = {
            "config": desired_manifest_header,
            "generated_at": int(time.time()),
            "per_student": {},
        }

        notebook_file_mode = 0o644 | (S_IWGRP if groupshared else 0)
        notebook_dir_mode = 0o755 | ((S_ISGID | S_IWGRP) if groupshared else 0)

        for student in students:
            seed_value = _seed(seed_salt, course_slug, assignment, student)
            rng = random.Random(seed_value)
            selected = draw_questions(
                question_ids, weights, subtopics, pick_count, rng, one_per_subtopic
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
            notebook_dir = output_dir / "students" / student / assignment
            notebook_file_path = notebook_dir / f"{assignment}.ipynb"
            _write_json(
                notebook_file_path,
                generated_notebook,
                file_mode=notebook_file_mode,
                dir_mode=notebook_dir_mode,
            )
            if question_files_root is not None:
                _copy_question_files(
                    question_files_root,
                    selected,
                    notebook_dir / question_files_root.name,
                    file_mode=notebook_file_mode,
                    dir_mode=notebook_dir_mode,
                )

            manifest["per_student"][student] = {
                "seed": seed_value,
                "selected_question_ids": selected,
                "path": str(notebook_file_path),
            }
        file_mode = 0o600 | (S_IWGRP | S_IRGRP if groupshared else 0)
        dir_mode = 0o700 | (0o070 | S_ISGID if groupshared else 0)
        _write_json(
            manifest_file_path,
            manifest,
            file_mode=file_mode,
            dir_mode=dir_mode,
        )

        if logger is None:
            print(
                f"Generated randomised notebooks for {len(students)} students "
                f"in {output_dir}/students/*/{assignment}, and manifest at {manifest_file_path}"
            )
        else:
            logger.info(
                "Generated randomised notebooks for %d students in %s/students/*/%s, and manifest at %s",
                len(students),
                output_dir,
                assignment,
                manifest_file_path,
            )
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
