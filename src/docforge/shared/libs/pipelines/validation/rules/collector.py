# ====== Code Summary ======
# The shared issue accumulator handed to every validation rule. It owns the growing list of issues
# and the single recording point (log + append) so each rule stays a pure check that only decides
# WHAT is wrong, never HOW it is stored. The validator collects ALL issues rather than failing on
# the first, so a UI can show everything wrong at once.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from ..issues import ValidationCode, ValidationIssue


class IssueCollector(LoggerClass):
    """
    Accumulates validation issues across every rule of a single validate() pass.

    One instance is created per graph validation and threaded through all rules, so the ordering of
    recorded issues mirrors the order in which the rules run.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self.issues: list[ValidationIssue] = []

    def record(self, code: ValidationCode, location: str, message: str) -> None:
        """
        Log and collect a single issue.

        Args:
            code (ValidationCode): The issue category.
            location (str): Where it was found (e.g. ``group 'ingest' / node 'chunk'``).
            message (str): Human-readable explanation.
        """
        self.logger.debug(f"validation issue [{code}] {location}: {message}")
        self.issues.append(ValidationIssue(code=code, location=location, message=message))


__all__ = ["IssueCollector"]
