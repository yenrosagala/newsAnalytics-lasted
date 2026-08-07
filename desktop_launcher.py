"""
Desktop launcher: runs the Streamlit server as a background process, then
opens a native app window (via pywebview) pointing at it -- so it feels
like a real Windows application instead of a browser tab.

This is the entry point you build into a .exe with PyInstaller. See
BUILD_WINDOWS.md in this same folder for the exact build command.

For quick local use without building an .exe at all, just double-click
run_app.bat instead -- it does the same thing but opens your default
browser rather than a dedicated app window.
"""
import os
import socket
import subprocess
import sys
import time

import webview

APP_PORT = 8765


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _resource_path(relative_path: str) -> str:
    """Resolve a path both when running as a plain .py script and when
    running as a PyInstaller-frozen .exe (which extracts bundled files to
    a temporary _MEIPASS folder at runtime)."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def main():
    entry_script = _resource_path("streamlit_app.py")

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", entry_script,
            "--server.port", str(APP_PORT),
            "--server.headless", "true",       # don't let Streamlit open its own browser tab
            "--browser.gatherUsageStats", "false",
        ],
        cwd=_resource_path("."),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    # Wait for the Streamlit server to actually accept connections before
    # opening the window, otherwise the window shows a blank/error page.
    server_ready = False
    for _ in range(60):  # up to ~30s
        if _port_is_open(APP_PORT):
            server_ready = True
            break
        time.sleep(0.5)

    if not server_ready:
        webview.create_window(
            "NewsAnalytics AI - Startup Error",
            html="<h2 style='font-family:sans-serif;padding:2rem'>"
                 "The app server didn't start in time. Close this window, "
                 "then check that Python and dependencies are installed correctly.</h2>",
            width=600, height=300,
        )
        webview.start()
        proc.terminate()
        return

    webview.create_window(
        "NewsAnalytics AI - Decision Intelligence Platform",
        f"http://localhost:{APP_PORT}",
        width=1400,
        height=900,
        min_size=(1000, 700),
    )
    webview.start()

    # When the window is closed, shut down the background Streamlit process too.
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


if __name__ == "__main__":
    main()