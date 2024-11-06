from math import ceil
from textwrap import dedent

from nbgrader.plugins import BasePlugin
from traitlets import Float, Int, List


class AaltoBasePlugin(BasePlugin):
    student_exemptions = List(
        default_value=[],
        help=dedent(
            """
            Allows specified students to be exempted
            from the late submission penalty
            """
        ),
    ).tag(config=True)

    penalty_unit = Float(
        default_value=0.0,
        help=dedent(
            """
            The penalty unit for each plugin. For instance, the value 0.2 for
            `SubRatio` means that submission will receive 20% penalty; whereas
            the value 1 for `SubMarks` means 1 mark penalty per each hour late
            """
        ),
    ).tag(config=True)

    penalty_cutoff = Int(
        default_value=0,
        help=dedent(
            """
            The cutoff point for score deduction. For instance, `SubFixed`
            awards a score of zero after the submission is late more than the
            number of seconds set here. Set to 0 to disable.
            """
        ),
    ).tag(config=True)

    def late_submission_penalty(self, student_id, score, total_seconds_late):
        raise NotImplementedError


class SubMarks(AaltoBasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of fixed marks per hour late"""

        if student_id in self.student_exemptions:
            return 0

        hours_late = round(total_seconds_late / 3600, 0)
        return hours_late * self.penalty_unit


class SubStep(AaltoBasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of fixed marks per every three hours late"""

        if student_id in self.student_exemptions:
            return 0

        hours_late = total_seconds_late / 3600
        three_hours = ceil(hours_late / 3)
        return three_hours * self.penalty_unit


class SubRatio(AaltoBasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of fixed ratio per day late"""

        if student_id in self.student_exemptions:
            return 0

        hours_late = total_seconds_late / 3600
        day_late = ceil(hours_late / 24)
        return day_late * self.penalty_unit * score


class SubFixed(AaltoBasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of fixed ratio after deadline, until cutoff"""

        if student_id in self.student_exemptions:
            return 0

        if self.penalty_cutoff and total_seconds_late > self.penalty_cutoff:
            # Award a score of zero after the cutoff point
            return score

        return self.penalty_unit * score
