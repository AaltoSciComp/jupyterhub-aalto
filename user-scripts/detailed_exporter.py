import sys

import numpy as np

from nbgrader.plugins import ExportPlugin, BasePlugin
from nbgrader.api import MissingEntry
from datetime import datetime
from traitlets import Type, Unicode, Bool

import pandas as pd

DEBUG = True


def dprint(msg):
    if DEBUG: print()


class DetailedExportPlugin(ExportPlugin):
    """CSV exporter plugin with detailed task grades for assignment."""

    username_suffix = Unicode(
        '@aalto.fi',
        help="Suffix for usernames, e.g. to add the domain.",
    ).tag(config=True)

    penalty_plugin = Type(
        None,
        allow_none=True,
        klass=BasePlugin,
        help="The plugin class for assigning the late penalty for each notebook. Defining this, user can change the penalty points assigned within the database."
    ).tag(config=True)

    scale_to_100 = Bool(
        True,
        help="Scale points to a scale of 100 (default True)."
    ).tag(config=True)

    def export(self, gradebook):
        if not self.assignment:
            raise ValueError("You must specify at least one assignment name to export.")

        if not set(self.assignment).issubset(map(lambda a: a.name, gradebook.assignments)):
            raise ValueError("The assignment name specified does not exist in the database.")

        if self.to == "":
            timestamp = datetime.now().replace(microsecond=0).isoformat()
            dest = f"grades_export_detailed_{timestamp}.csv"
        else:
            dest = self.to

        self.log.info("Exporting grades to %s", dest)

        report = pd.DataFrame({"username": list(map(lambda std: std.id + self.username_suffix, gradebook.students))},
                              index=gradebook.students)
        delimiter = "/"

        for assignment_name in self.assignment:
            assignment = gradebook.find_assignment(assignment_name)
            grade_cells = gradebook.find_assignment_gradecells(assignment.name)

            grade_names = list()
            prefix = "" if len(self.assignment) == 1 else f"{assignment.name}{delimiter}"
            for grade_cell in grade_cells:
                nb_prefix = "" if len(assignment.notebooks) == 1 else f"{grade_cell.notebook.name}{delimiter}"
                grade_names.append(f"{prefix}{nb_prefix}{grade_cell.name}")
            report.loc[:, grade_names + [assignment.name]] = np.nan

            for student in gradebook.students:
                # Assignment total grade
                try:
                    submission = gradebook.find_submission(assignment.name, student.id)
                except MissingEntry:
                    final_score = 0.0
                else:
                    penalty = submission.late_submission_penalty
                    if self.penalty_plugin:
                        if submission.total_seconds_late > 0:
                            penalty = self.penalty_plugin.late_submission_penalty(student.id, submission.score,
                                                                                  submission.total_seconds_late)

                    score = max(0.0, (submission.score - penalty))
                    if self.scale_to_100:
                        try:
                            score = (score / assignment.max_score * 100)
                        except ZeroDivisionError:
                            score = 0
                    final_score = score

                # Detailed cell grades
                grades = gradebook.find_all_grades(assignment.name, student.id)
                for grade in grades:
                    nb_prefix = "" if len(assignment.notebooks) == 1 else f"{grade.notebook.name}{delimiter}"
                    grade_name = f"{prefix}{nb_prefix}{grade.name}"
                    report.loc[student, grade_name] = grade.score

                report.loc[student, assignment.name] = final_score

        report \
            .fillna("") \
            .to_csv(dest, index=False)
