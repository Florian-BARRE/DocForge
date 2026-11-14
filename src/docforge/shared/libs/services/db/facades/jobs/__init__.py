# ====== Code Summary ======
# Split of the jobs façade by responsibility. ``JobsFacade`` (jobs/jobs_facade.py) is the public
# surface behind ``Database.jobs`` and delegates to JobQueryOps (reads), JobLifecycleOps (lifecycle,
# timeline, heartbeats, retention) and JobReaperOps (force-termination and reaping); import the
# façade, not those internal collaborators, from outside.

from .jobs_facade import JobsFacade

__all__ = ["JobsFacade"]
