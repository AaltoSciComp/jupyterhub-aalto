#!/usr/bin/env python3
"""Custom nbgrader fetch plugin for per-student randomized assignments.

This plugin keeps the normal nbgrader exchange flow and only alters fetch:
1. Perform the standard fetch from exchange outbound.
2. If a randomization manifest exists for the assignment and student, replace
   the fetched notebook with the pre-generated student-specific notebook.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from nbgrader.exchange.default.fetch_assignment import ExchangeFetchAssignment
from traitlets import Unicode


class RandomizedExchangeFetchAssignment(ExchangeFetchAssignment):
    """Fetch plugin that overlays randomized notebook variants per student."""

    randomization_root = Unicode(
        "",
        help=(
            "Root directory containing randomized assignment outputs, for example "
            "'/courses/<slug>/files/randomized'."
        ),
    ).tag(config=True)

    # def _manifest_path(self) -> str:
    #     return os.path.join(
    #         self.randomization_root,
    #         self.coursedir.assignment_id,
    #         "_randomization_manifest.json",
    #     )

    def _randomized_notebook(self) -> str | None:
        if not self.randomization_root:
            return None

        manifest_path = (
            Path(self.randomization_root)
            / self.coursedir.assignment_id
            / "_randomization_manifest.json"
        )
        if not os.path.isfile(manifest_path):
            return None

        student_id = self.coursedir.student_id
        if not student_id:
            return None

        with open(manifest_path, encoding="utf-8") as fp:
            manifest = json.load(fp)

        per_student = manifest.get("per_student") or {}
        student_info = per_student.get(student_id)
        if not isinstance(student_info, dict):
            return None

        notebook_path = student_info.get("path")
        if not isinstance(notebook_path, str):
            return None
        if not os.path.isfile(notebook_path):
            return None
        return notebook_path

    def copy_files(self):
        # First run the standard fetch workflow from exchange outbound.
        super().copy_files()

        randomized_path = self._randomized_notebook()
        if randomized_path is None:
            return

        dest_name = os.path.basename(randomized_path)
        dest_path = os.path.join(self.dest_path, dest_name)
        self.log.info(
            "Applying randomized variant for %s from %s",
            self.coursedir.student_id,
            randomized_path,
        )
        shutil.copyfile(randomized_path, dest_path)
