"""Worker entry point.

    uv run python -m app.tasks.run_worker

Replaces `arq app.tasks.worker.WorkerSettings`. arq's CLI builds the Worker
with `asyncio.get_event_loop()` before any loop exists — that quietly created
one until Python 3.10, and raises from 3.14:

    RuntimeError: There is no current event loop in thread 'MainThread'

Creating the loop first sidesteps it. Nothing about the worker's behaviour
changes; this only fixes how it starts up.
"""

import asyncio
import logging

from arq.worker import create_worker

from app.tasks.worker import WorkerSettings


def main() -> None:
    # arq logs through the standard library and attaches no handler of its
    # own, so without this the worker runs completely silently — which looks
    # identical to it having failed to start.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Must exist before `create_worker`, which reads it during construction
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    worker = create_worker(WorkerSettings)  # type: ignore[arg-type]
    try:
        worker.run()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
