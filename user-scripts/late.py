from __future__ import division
from nbgrader.plugins import BasePlugin
from math import ceil


class SubMarks(BasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of 1 mark per hour late"""

        penalty_unit = 1
        hours_late = round(total_seconds_late / 3600, 0)
        return hours_late * penalty_unit


class SubStep(BasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of 10 marks per every three hours late"""

        penalty_unit = 10
        hours_late = total_seconds_late / 3600 
        three_hours = ceil(hours_late / 3)
        return three_hours * penalty_unit


class SubRatio(BasePlugin):
    def late_submission_penalty(self, student_id, score, total_seconds_late):
        """Penalty of 20% score per day late"""
        
        penalty_unit = 0.2 * score
        hours_late = total_seconds_late / 3600 
        day_late = ceil(hours_late / 24)
        return day_late * penalty_unit
