# ====== Code Summary ======
# One setup for the whole suite: the loggerplusplus sinks are reset around every test, so a test that
# installs sinks (LoggingBootstrap) never leaks them into the next one.

# ====== Standard Library Imports ======
from collections.abc import Iterator

# ====== Third-Party Library Imports ======
import pytest
from loggerplusplus import loggerplusplus


@pytest.fixture(autouse=True)
def _reset_log_sinks() -> Iterator[None]:
    """Give every test a clean set of sinks and restore the library default afterwards."""
    yield
    loggerplusplus.remove()
