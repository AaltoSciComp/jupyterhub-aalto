import shutil
from pathlib import Path

from nbgrader.exchange.default.list import ExchangeList
from traitlets.traitlets import Unicode


class RandomisedExchangeList(ExchangeList):
    """Remove standard and per-student randomised assignment releases."""

    randomisation_root = Unicode(
        "",
        help="Root directory containing randomised assignment outputs.",
    ).tag(config=True)

    def remove_files(self):
        assignments = super().remove_files()

        # Randomised files are release artifacts.  Inbound and cached removal
        # must retain them because those modes remove submissions instead.
        if self.inbound or self.cached:
            return assignments

        if not self.randomisation_root:
            self.log.warning(
                "RandomisedExchangeList.randomisation_root is not configured; "
                "randomised assignment files were not removed"
            )
            return assignments

        root = Path(self.randomisation_root)
        assignment_ids = {info["assignment_id"] for info in assignments}
        for assignment_id in assignment_ids:
            if Path(assignment_id).name != assignment_id:
                self.log.warning(
                    "Refusing to remove randomised files for invalid assignment ID %r",
                    assignment_id,
                )
                continue

            self.log.info("Removing randomised files for assignment %s", assignment_id)
            students_root = root / "students"
            if students_root.is_dir():
                for student_dir in students_root.iterdir():
                    if not student_dir.is_dir():
                        continue
                    assignment_dir = student_dir / assignment_id
                    if assignment_dir.is_dir():
                        shutil.rmtree(assignment_dir)
                    if not any(student_dir.iterdir()):
                        student_dir.rmdir()

            manifest_dir = root / "manifests" / assignment_id
            if manifest_dir.is_dir():
                shutil.rmtree(manifest_dir)

            # Older versions of the release plugin created this empty lock
            # directory in addition to the students and manifests trees.
            legacy_assignment_dir = root / assignment_id
            if legacy_assignment_dir.is_dir():
                shutil.rmtree(legacy_assignment_dir)

        for directory in (root / "students", root / "manifests"):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()

        return assignments
