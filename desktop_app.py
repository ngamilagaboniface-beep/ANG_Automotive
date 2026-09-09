"""
ANG Automotive - Standalone Desktop GUI Application & Windows Executable Entry Point.
Runs the background DoIP & UDS Flask server and launches a dedicated native desktop application window.
"""

import os
import sys
import time
import socket
import threading
import webbrowser
import logging

# Ensure resource paths resolve correctly when bundled as PyInstaller .exe
if getattr(sys, 'frozen', False):
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    basedir = sys._MEIPASS
    os.chdir(basedir)
else:
    basedir = os.path.abspath(os.path.dirname(__file__))

from app import app, doip_server

logger = logging.getLogger("ANG_Desktop")

def find_free_port(preferred_port=5000):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', preferred_port))
            return preferred_port
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]

def start_backend_server(port):
    """Starts the Flask server in background thread."""
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)

def open_browser_app_mode(url):
    """Attempts to launch Chrome / Edge in clean app mode (without browser toolbars)."""
    # Try Microsoft Edge in app mode (default on Windows 10/11)
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    # Try Google Chrome
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]

    for p in edge_paths + chrome_paths:
        if os.path.exists(p):
            try:
                import subprocess
                subprocess.Popen([p, f"--app={url}", "--window-size=1440,900"])
                return True
            except Exception:
                pass

    # Fallback to standard default browser
    webbrowser.open(url)
    return True

def main():
    port = find_free_port(5000)
    server_url = f"http://127.0.0.1:{port}"

    # 1. Start Background Flask & DoIP Server
    server_thread = threading.Thread(target=start_backend_server, args=(port,), daemon=True)
    server_thread.start()

    # Wait for server to bind
    time.sleep(1.2)

    # 2. Try launching Native Desktop Window via PyWebView
    use_webview = True
    try:
        import webview
        # Create Desktop Window
        window = webview.create_window(
            title="ANG Automotive - BMW Diagnostic & Remote ECU Tuning Platform",
            url=server_url,
            width=1480,
            height=920,
            min_size=(1024, 700),
            background_color="#0a0c10"
        )
        webview.start(debug=False)
    except Exception as e:
        logger.info(f"Native webview not active, launching system app browser: {e}")
        use_webview = False

    if not use_webview:
        # Launch browser in app mode
        open_browser_app_mode(server_url)
        print(f"\n=======================================================")
        print(f" ANG Automotive Platform Active on: {server_url}")
        print(f" Close this window to stop the application.")
        print(f"=======================================================\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down ANG Automotive...")

if __name__ == '__main__':
    main()
