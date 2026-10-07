"""Custom nbgrader fetch plugin for per-student randomised assignments.

This plugin keeps the normal nbgrader exchange flow and only alters fetch:
1. Perform the standard fetch from exchange outbound.
2. If a randomisation manifest exists for the assignment and student, replace
   the fetched notebook with the pre-generated student-specific notebook.
"""

from __future__ import annotations

import getpass
from pathlib import Path

from nbgrader.exchange.default.fetch_assignment import ExchangeFetchAssignment


class RandomisedExchangeFetchAssignment(ExchangeFetchAssignment):
    """Fetch plugin that overlays randomised notebook variants per student."""

    def copy_files(self):
        self.log.info("RandomisedExchangeFetchAssignment: copy_files()")

        # The student ID defaults to a wildcard, we want the actual ID here
        if self.coursedir.student_id == "*":
            student_id = getpass.getuser()
        else:
            student_id = str(self.coursedir.student_id)
        self.log.info(f"{student_id=}")

        assignment_id = str(self.coursedir.assignment_id)

        random_path = Path("/srv/nbgrader/per-student-randomised") / assignment_id
        random_notebook_path = random_path / f"{assignment_id}.ipynb"
        if not random_notebook_path.is_file():
            self.log.error(
                "no random notebook found for %s: %s", student_id, random_notebook_path
            )
            return

        # First run the standard fetch workflow from exchange outbound
        super().copy_files()

        self.log.info(
            "Applying randomised variant for %s from %s",
            student_id,
            random_notebook_path,
        )
        # Then copy the per-student notebook and any other files
        self.do_copy(random_path, self.dest_path)
