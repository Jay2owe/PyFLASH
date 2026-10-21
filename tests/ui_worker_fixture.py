"""Bounded CPU fixture followed by the real saved-analysis loading call.

Used only by the browser responsiveness check, never dispatched by production.
It spends 25 seconds on one CPU, verifies its deterministic checksum, then calls
the normal saved-state reader on the already processed source. No raw data is
reprocessed and no source files are written. This checks responsiveness while
CPU work runs; it does not assert that a legacy pickle is a valid factory cache.
"""
import hashlib
import sys
import time


def main():
    from PyFLASH.ui import jobs, services
    from PyFLASH._logging import logger
    from PyFLASH.ui import workspace
    import json
    from pathlib import Path
    request_path = Path(sys.argv[1])
    request = json.loads(request_path.read_text())
    source = Path(request["project"]["pickle_path"]) / (request["project"]["name"] + ".pkl")
    original = workspace.content_hash(source)
    def busy_create(*args, **kwargs):
        payload = b"PyFLASH bounded CPU responsiveness fixture" * 4096
        expected = hashlib.sha256(payload).digest()
        deadline = time.perf_counter() + 25
        rounds = 0
        logger.status("Running bounded CPU responsiveness check; original data is read-only.")
        while time.perf_counter() < deadline:
            assert hashlib.sha256(payload).digest() == expected
            rounds += 1
        logger.status(f"CPU fixture checksum verified for {rounds} rounds.")
        return services.open_pickle(str(source))
    state = jobs.run_request(request_path, create=busy_create)
    assert workspace.content_hash(source) == original
    return 0 if state["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
