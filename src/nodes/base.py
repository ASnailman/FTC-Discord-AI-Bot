"""Node contract for the retrieval pipeline.

A node is any callable `(state) -> NodeResult`. `@retrieval_node(name)`
wraps a node body so it can never raise -- an unhandled exception in one
source must never take down `/ask`; `stats` and `chroma` (which always run,
see `chain.py`) are what guarantee the pipeline can always answer even if
every external node fails.
"""
import concurrent.futures
import functools
import time
from dataclasses import dataclass

from logging_setup import get_logger

logger = get_logger(__name__)

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_DISABLED = "disabled"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"


@dataclass(frozen=True)
class NodeResult:
    source: str
    status: str
    text: str = ""
    citations: tuple = ()
    # Reason for a non-ok status; logged server-side only, NEVER sent to
    # Discord (an exception's str() can contain paths or partial secrets --
    # see docs/security.md).
    detail: str = ""

    def __repr__(self):
        return f"NodeResult(source={self.source!r}, status={self.status!r}, len(text)={len(self.text)})"


@dataclass(frozen=True)
class PipelineState:
    question: str
    team_nums: tuple
    season: "int | None" = None
    region: "str | None" = None
    team_names: tuple = ()  # resolved names for the identified team_nums, if known


def retrieval_node(source: str):
    """Decorate a node body `(state) -> NodeResult` so it can never raise."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state: PipelineState) -> NodeResult:
            try:
                return fn(state)
            except Exception as exc:  # noqa: BLE001 -- a node must never crash the pipeline
                logger.exception("node %s failed", source)
                return NodeResult(source=source, status=STATUS_ERROR, detail=str(exc))
        wrapper._node_source = source
        return wrapper
    return decorator


def run_nodes(nodes: dict, state: PipelineState, *, node_timeout: float, total_budget: float) -> dict:
    """Run every node in `nodes` (name -> callable) concurrently.

    Bounded by `total_budget` overall; a node still running past that is
    reported as `status="timeout"` rather than awaited further. The worker
    thread itself is not force-killed (Python threads can't be) -- it's
    left to die on its own once the HTTP call inside it hits its own
    `timeout=` (every tools.http call is required to pass one <=
    `node_timeout`), so nothing leaks past a few extra seconds.
    """
    if not nodes:
        return {}

    results: dict[str, NodeResult] = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes))
    futures = {executor.submit(fn, state): name for name, fn in nodes.items()}
    deadline = time.monotonic() + total_budget

    try:
        for future in concurrent.futures.as_completed(futures, timeout=total_budget):
            name = futures[future]
            remaining = max(0.01, min(node_timeout, deadline - time.monotonic()))
            try:
                results[name] = future.result(timeout=remaining)
            except concurrent.futures.TimeoutError:
                logger.warning("node %s exceeded its timeout", name)
                results[name] = NodeResult(source=name, status=STATUS_TIMEOUT)
            except Exception as exc:  # noqa: BLE001 -- defense in depth if a node skips @retrieval_node
                logger.exception("node %s raised outside its decorator", name)
                results[name] = NodeResult(source=name, status=STATUS_ERROR, detail=str(exc))
    except concurrent.futures.TimeoutError:
        still_running = [n for f, n in futures.items() if not f.done()]
        logger.warning("pipeline budget exhausted with nodes still running: %s", still_running)
    finally:
        # Don't block the response on abandoned threads; they die on their
        # own request timeout shortly after (tools.http enforces
        # timeout <= node_timeout on every call).
        executor.shutdown(wait=False)

    for name in nodes:
        results.setdefault(name, NodeResult(source=name, status=STATUS_TIMEOUT))

    return results
