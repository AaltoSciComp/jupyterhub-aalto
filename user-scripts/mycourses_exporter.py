#MyCoursesExporter.py
#
# nbgrader exporter in MyCourses format.  Originally written by Joakim
# Järvinen.
#
#
# License: BSD 3-clause (same as nbgrader)
#
#
#  Copyright (c) 2019-2020 the contributors
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
#  1. Redistributions of source code must retain the above copyright notice, this
#     list of conditions and the following disclaimer.
#
#  2. Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
#  3. Neither the name of the copyright holder nor the names of its
#     contributors may be used to endorse or promote products derived from
#     this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
#  FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
#  DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#  SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#  OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


from nbgrader.plugins import ExportPlugin, BasePlugin
from nbgrader.api import MissingEntry
from datetime import datetime
from traitlets import Type, Unicode, Bool

class MyCoursesExportPlugin(ExportPlugin):
    """CSV exporter plugin for Aalto MyCourses."""

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
        if self.to == "":
            dest = f"grades_export_mycourses_{datetime.now().replace(microsecond=0).isoformat()}.csv"
        else:
            dest = self.to

        self.log.info("Exporting grades to %s", dest)

        fh = open(dest, "w")

        # Generete a format string for each row entry
        keys = ['username']
        keys.extend(self.assignment)
        fh.write(",".join(keys) + "\n")

        # Loop over each student in the database
        for student in gradebook.students:

            # Create a dictionary that will store information about this
            # student's scores for all assignments
            student_row = {}

            # Loop over each specified assignment
            for assignment_name in self.assignment:
                assignment = gradebook.find_assignment(assignment_name)

                student_row['username'] = student.id + self.username_suffix
                # Try to find the submission in the database. If it doesn't
                # exist, the `MissingEntry` exception will be raised, which
                # means the student didn't submit anything, so we assign them a
                # score of zero.
                try:
                    submission = gradebook.find_submission(assignment.name, student.id)
                except MissingEntry:
                    student_row[assignment.name] = 0.0
                else:
                    penalty = submission.late_submission_penalty
                    if self.penalty_plugin:
                        if submission.total_seconds_late > 0:
                            penalty = self.penalty_plugin.late_submission_penalty(student.id, submission.score, submission.total_seconds_late)

                    score = max(0.0, (submission.score - penalty))
                    # Set the score between 0 and 100 which is the most common
                    # scoring schema used in Aalto MyCourses
                    if self.scale_to_100:
                        try:
                            score =  (score / assignment.max_score * 100)
                        except ZeroDivisionError:
                            score = 0
                    student_row[assignment.name] = score
                for key in student_row:
                    if student_row[key] is None:
                        student_row[key] = ''
                    if not isinstance(student_row[key], str):
                        student_row[key] = str(student_row[key])

            fh.write(",".join(student_row.values()) + "\n")

        fh.close()
