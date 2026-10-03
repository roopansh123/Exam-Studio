import sys
import os
import threading
import time
import socket
import asyncio
import urllib.request
import multiprocessing
import webbrowser

# Add current folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from app.main import app
from app.database import init_db

server_instance = None

def find_available_port(preferred=8000):
    """Finds an available TCP port starting from preferred, falling back if busy."""
    candidate_ports = [preferred, 8001, 8080, 8888, 5000]
    for port in candidate_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue

    # If all preferred candidates are occupied, ask OS for an ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def run_uvicorn_server(host, port):
    """Runs Uvicorn in a dedicated background thread with an explicit asyncio event loop."""
    global server_instance
    try:
        # Create and set a fresh event loop for this thread (essential on Windows)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            loop="asyncio",
            access_log=False
        )
        server_instance = uvicorn.Server(config)
        loop.run_until_complete(server_instance.serve())
    except Exception as e:
        print(f"Error running uvicorn server on {host}:{port}: {e}")

def wait_for_server_ready(port, timeout=25):
    """Actively polls the server until HTTP 200 is confirmed before opening the UI."""
    start_time = time.time()
    url = f"http://127.0.0.1:{port}/api/school-settings"
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LKCS-Desktop-HealthCheck'})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False

def main():
    # 1. Initialize Database & Seeding
    try:
        init_db()
    except Exception as e:
        print(f"Database initialization notice: {e}")

    # 2. Determine Port & Start Background Server on Loopback
    port = find_available_port(8000)
    server_thread = threading.Thread(
        target=run_uvicorn_server,
        args=("127.0.0.1", port),
        daemon=True
    )
    server_thread.start()

    # 3. Actively wait until the server is responsive
    print(f"Waiting for internal LKCS server to be ready on port {port}...")
    server_ok = wait_for_server_ready(port, timeout=20)
    if not server_ok:
        print(f"[Warning] Server health check timed out on port {port}, proceeding anyway...")

    app_url = f"http://127.0.0.1:{port}"

    # 4. Clean exit callback
    def on_window_closed():
        global server_instance
        if server_instance:
            server_instance.should_exit = True
        os._exit(0)

    # 5. Launch PyWebView Desktop Window
    try:
        import webview
        print(f"Launching LKCS Exam Studio Desktop Window at {app_url}...")
        window = webview.create_window(
            title="LKCS Exam Studio - Lord Krishna Convent School",
            url=app_url,
            width=1280,
            height=850,
            min_size=(960, 640),
            resizable=True
        )
        window.events.closed += on_window_closed
        webview.start()
    except Exception as e:
        print(f"Native window not available ({e}). Launching in default web browser...")
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
            on_window_closed()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
