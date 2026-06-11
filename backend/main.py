"""Convenience launcher. Prefer `uv run raspy` or `uvicorn raspy.app:app`.

This thin shim lets `python main.py` start the spine too.
"""

from raspy.__main__ import main

if __name__ == "__main__":
    main()
