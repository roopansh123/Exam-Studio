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

import traceback
import logging

# Set up desktop log file
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lkcs_desktop.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def log_msg(msg):
    print(msg)
    logging.info(msg)

def log_err(msg):
    print(msg, file=sys.stderr)
    logging.error(msg)

server_instance = None

def find_available_port(preferred=8000):
    """Finds an available TCP port starting from preferred, falling back if busy."""
    candidate_ports = [preferred, 8001, 8080, 8888, 5000]
    for port in candidate_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue

    # If all preferred candidates are occupied, ask OS for an ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def run_uvicorn_server(host, port):
    """Runs Uvicorn in a dedicated background thread with an explicit event loop."""
    global server_instance
    log_msg(f"Initializing Uvicorn on {host}:{port}...")
    try:
        # Create and assign a dedicated loop for this thread
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
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
        log_msg("Uvicorn server starting loop...")
        loop.run_until_complete(server_instance.serve())
        log_msg("Uvicorn server exited cleanly.")
    except Exception as e:
        log_err(f"CRITICAL: Uvicorn server crash on {host}:{port}: {e}\n{traceback.format_exc()}")

def wait_for_server_ready(port, timeout=35):
    """Actively polls the server with raw socket + proxy-bypass HTTP check until ready."""
    start_time = time.time()
    url = f"http://127.0.0.1:{port}/"
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    while time.time() - start_time < timeout:
        # 1. First probe raw TCP socket connection
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    # 2. Port is accepting connections, verify HTTP layer
                    req = urllib.request.Request(url, headers={'User-Agent': 'LKCS-HealthCheck'})
                    try:
                        with opener.open(req, timeout=1.0) as resp:
                            if resp.status in (200, 302, 307):
                                log_msg(f"Server confirmed ready on port {port} (HTTP {resp.status})")
                                return True
                    except urllib.error.HTTPError as he:
                        # Any HTTP status response means the web server is alive
                        log_msg(f"Server confirmed ready on port {port} (HTTP {he.code})")
                        return True
                    except Exception:
                        # Socket is open, wait one tick for full HTTP stack
                        time.sleep(0.3)
                        return True
        except Exception:
            pass
        time.sleep(0.25)
    return False

def main():
    log_msg("LKCS Exam Studio starting...")

    # 1. Initialize Database & Seeding
    try:
        init_db()
        log_msg("Database verified and initialized.")
    except Exception as e:
        log_err(f"Database initialization warning: {e}\n{traceback.format_exc()}")

    # 2. Determine Port & Start Background Server on Loopback
    port = find_available_port(8000)
    log_msg(f"Assigned local port: {port}")

    server_thread = threading.Thread(
        target=run_uvicorn_server,
        args=("127.0.0.1", port),
        daemon=True
    )
    server_thread.start()

    # 3. Actively wait until the server is responsive
    log_msg(f"Waiting for local server to be ready on port {port}...")
    server_ok = wait_for_server_ready(port, timeout=35)
    if not server_ok:
        log_err(f"[ERROR] Server health check timed out on port {port}.")

    app_url = f"http://127.0.0.1:{port}"

    # 4. Clean exit callback
    def on_window_closed():
        global server_instance
        log_msg("Desktop window closed by user. Terminating...")
        if server_instance:
            server_instance.should_exit = True
        os._exit(0)

    # 5. Launch PyWebView Desktop Window
    try:
        import webview
        log_msg(f"Launching PyWebView Desktop Window at {app_url}...")
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
        log_err(f"Native window not available ({e}). Launching in default web browser...")
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
