"""Execute an admitted processing request outside the browser server."""
import sys


def main():
    from PyFLASH.ui.jobs import run_request
    state = run_request(sys.argv[1])
    return 0 if state["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
