from nbgrader.plugins import ExportPlugin, BasePlugin
from nbgrader.api import MissingEntry
from datetime import datetime
from traitlets import Type, Unicode, Bool

from collections import defaultdict, OrderedDict


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
        all_assignments = list(map(lambda a: a.name, gradebook.assignments))
        if not set(self.assignment).issubset(all_assignments):
            raise ValueError("At least one assignment name specified does not exist in the database.")

        if not self.assignment:
            self.assignment = all_assignments

        self.log.info("Exporting assignments: %s", self.assignment)

        if self.to == "":
            timestamp = datetime.now().replace(microsecond=0).isoformat()
            dest = f"grades_export_detailed_{timestamp}.csv"
        else:
            dest = self.to

        self.log.info("Exporting grades to %s", dest)

        # report = pd.DataFrame({"username": list(map(lambda std: std.id + self.username_suffix, gradebook.students))},
        #                    index=gradebook.students)
        report = defaultdict(OrderedDict)
        columns = list()
        delimiter = "/"

        for assignment_name in self.assignment:
            assignment = gradebook.find_assignment(assignment_name)
            prefix = "" if len(self.assignment) == 1 else f"{assignment.name}{delimiter}"

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

                    # Detailed task grades
                    notebooks = submission.notebooks
                    for notebook in notebooks:
                        for grade in notebook.grades:
                            nb_prefix = "" if len(notebooks) == 1 else f"{grade.notebook.name}{delimiter}"
                            grade_name = f"{prefix}{nb_prefix}{grade.name}"

                            if grade_name not in columns:
                                columns.append(grade_name)
                            report[grade.student][grade_name] = grade.score

                report[student][assignment.name] = final_score
            columns.append(assignment.name)

        with open(dest, "w") as f:
            f.write("username," + ",".join(columns) + "\n")
            for student in report.keys():
                f.write(f"{student.id + self.username_suffix},")
                f.write(",".join(str(report[student][assignment]) if assignment in report[student] else ""
                                 for assignment in columns) + "\n")
