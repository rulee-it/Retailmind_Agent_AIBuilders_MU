"""Entry point: `python run.py` boots the FastAPI server and opens the browser."""
from __future__ import annotations

import threading
import webbrowser

import uvicorn

URL = "http://127.0.0.1:8000"


def _open_browser() -> None:
    webbrowser.open(URL)


if __name__ == "__main__":
    threading.Timer(1.6, _open_browser).start()
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
