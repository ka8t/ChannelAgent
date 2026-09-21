"""Liveness signal for the container healthcheck (#48).

While the application runs, `heartbeat()` touches a file every few seconds,
and only while at least one component (adapter, Admin API) is still running.
The Docker healthcheck runs `python -m app.health`, which succeeds when that
file is recent. A process that is alive but has lost all its components, or
whose event loop is stuck, stops touching the file and turns `unhealthy`
after `MAX_AGE_SECONDS`. No network port and no data involved, so it works
with or without the Admin API.

Stdlib only, on purpose: the check starts a fresh Python every interval.
"""

import asyncio
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

HEARTBEAT_PATH = Path(tempfile.gettempdir()) / "channelagent.heartbeat"
INTERVAL_SECONDS = 15
MAX_AGE_SECONDS = 60


def beat(path: Path | None = None) -> None:
    (path or HEARTBEAT_PATH).touch()


async def heartbeat(components: Sequence[asyncio.Task], interval: float = INTERVAL_SECONDS) -> None:
    """Touch the heartbeat file while the application is doing its job: with no
    component at all it is idling on purpose, and counts as alive. Once every
    component has ended it stops, so the container turns unhealthy.
    """
    while not components or any(not task.done() for task in components):
        beat()
        await asyncio.sleep(interval)


def check(path: Path | None = None, max_age: float = MAX_AGE_SECONDS) -> tuple[bool, str]:
    target = path or HEARTBEAT_PATH
    try:
        age = time.time() - target.stat().st_mtime
    except FileNotFoundError:
        return False, f"no heartbeat file at {target}"
    if age > max_age:
        return False, f"last heartbeat {age:.0f} s ago (limit {max_age:.0f} s)"
    return True, f"last heartbeat {age:.0f} s ago"


def main() -> int:
    healthy, message = check()
    print(("healthy: " if healthy else "unhealthy: ") + message)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
