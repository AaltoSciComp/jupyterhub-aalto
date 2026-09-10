#!/usr/bin/env python3
"""Custom nbgrader fetch plugin for per-student randomised assignments.

This plugin keeps the normal nbgrader exchange flow and only alters fetch:
1. Perform the standard fetch from exchange outbound.
2. If a randomisation manifest exists for the assignment and student, replace
   the fetched notebook with the pre-generated student-specific notebook.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
from pathlib import Path

from nbgrader.exchange.default.fetch_assignment import ExchangeFetchAssignment
from traitlets import Unicode


class RandomisedExchangeFetchAssignment(ExchangeFetchAssignment):
    """Fetch plugin that overlays randomised notebook variants per student."""

    randomisation_root = Unicode(
        "",
        help=(
            "Root directory containing randomised assignment outputs, for example "
            "'/courses/<slug>/files/randomised'."
        ),
    ).tag(config=True)

    # def _manifest_path(self) -> str:
    #     return os.path.join(
    #         self.randomisation_root,
    #         self.coursedir.assignment_id,
    #         "_randomisation_manifest.json",
    #     )

    def _randomised_notebook(self, student_id: str) -> str | None:
        if not self.randomisation_root:
            self.log.warn("random fetch: no randomisation root")
            return None

        manifest_path = (
            Path(self.randomisation_root)
            / self.coursedir.assignment_id
            / "_randomisation_manifest.json"
        )
        if not os.path.isfile(manifest_path):
            self.log.warn("random fetch: no manifest path")
            return None

        if not student_id or student_id == "*":
            self.log.warn(
                "random fetch: No student ID provided, cannot fetch randomised notebook"
            )
            return None

        with open(manifest_path, encoding="utf-8") as fp:
            manifest = json.load(fp)

        per_student = manifest.get("per_student") or {}
        student_info = per_student.get(student_id)
        if not isinstance(student_info, dict):
            self.log.warn("random fetch: no student info")
            return None

        notebook_path = student_info.get("path")
        if not isinstance(notebook_path, str):
            self.log.warn("random fetch: no notebook path")
            return None
        if not os.path.isfile(notebook_path):
            self.log.warn("random fetch: notebook file not found")
            return None
        return notebook_path

    def copy_files(self):
        # First run the standard fetch workflow from exchange outbound.
        self.log.info("copy_files")

        # The student ID defaults to a wildcard, we want the actual ID here
        if self.coursedir.student_id == "*":
            student_id = getpass.getuser()
        else:
            student_id = self.coursedir.student_id
        self.log.info(f"{student_id=}")

        randomised_path = self._randomised_notebook(student_id=student_id)
        if randomised_path is None:
            self.log.warn("no random path")
            return

        super().copy_files()

        dest_name = os.path.basename(randomised_path)
        dest_path = os.path.join(self.dest_path, dest_name)
        self.log.info(
            "Applying randomised variant for %s from %s",
            student_id,
            randomised_path,
        )
        shutil.copyfile(randomised_path, dest_path)
