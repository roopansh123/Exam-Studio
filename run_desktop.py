import sys
import os

# In PyInstaller windowed mode (console=False), sys.stdout and sys.stderr are None.
# This causes Uvicorn's ColourizedFormatter (sys.stdout.isatty()) to crash with:
# AttributeError: 'NoneType' object has no attribute 'isatty'
class SafeStream:
    def isatty(self):
        return False
    def write(self, s):
        pass
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = SafeStream()
if sys.stderr is None:
    sys.stderr = SafeStream()
if sys.stdin is None:
    sys.stdin = SafeStream()

import threading
import time
import socket
import asyncio
import urllib.request
import multiprocessing
import webbrowser
import contextlib
import traceback
import logging

# Add current folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Explicit hidden imports for PyInstaller bundling
import anyio
import anyio._backends._asyncio
import uvicorn
import uvicorn.loops
import uvicorn.loops.auto
import uvicorn.loops.asyncio
import uvicorn.protocols
import uvicorn.protocols.http
import uvicorn.protocols.http.h11_impl
import uvicorn.lifespan
import uvicorn.lifespan.on

from app.main import app
from app.database import get_app_data_dir, init_db

# Set up desktop log file in writable user data folder (e.g. %APPDATA%\LKCSExamStudio on Windows)
try:
    LOG_DIR = get_app_data_dir()
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, "lkcs_desktop.log")
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
except Exception:
    try:
        import tempfile
        LOG_FILE = os.path.join(tempfile.gettempdir(), "lkcs_desktop.log")
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )
    except Exception:
        LOG_FILE = "console"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

def log_msg(msg):
    print(msg)
    logging.info(msg)

def log_err(msg):
    print(msg, file=sys.stderr)
    logging.error(msg)

def show_error_dialog(title, message, error_details=""):
    full_msg = message
    if error_details:
        full_msg += f"\n\nError details:\n{error_details}"
    log_err(f"[{title}] {full_msg}")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(full_msg), str(title), 0x10)
            return
        except Exception:
            pass

class BackgroundUvicornServer(uvicorn.Server):
    """Subclass of uvicorn.Server that disables signal handlers so it can run safely in a worker thread."""
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def capture_signals(self):
        yield

server_instance = None
server_error = None

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
    """Runs Uvicorn server in a dedicated background thread without lifespan or signal conflicts."""
    global server_instance, server_error
    log_msg(f"Initializing Uvicorn on {host}:{port}...")
    try:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            use_colors=False,
            log_config=None,
            lifespan="off"
        )
        server_instance = BackgroundUvicornServer(config)
        log_msg("Starting Uvicorn server via server.run()...")
        server_instance.run()
        log_msg("Uvicorn server finished.")
    except BaseException as e:
        server_error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        log_err(f"CRITICAL: Uvicorn server crash on {host}:{port}: {server_error}")

def wait_for_server_ready(port, timeout=35):
    """Waits for server_instance.started flag or socket connectivity."""
    global server_instance, server_error
    start_time = time.time()
    url = f"http://127.0.0.1:{port}/"
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    while time.time() - start_time < timeout:
        if server_error:
            log_err(f"Server initialization error detected: {server_error}")
            return False

        # 1. Check uvicorn started flag directly
        if server_instance and getattr(server_instance, 'started', False):
            log_msg(f"Server flag started=True confirmed on port {port}")
            return True

        # 2. Probe raw TCP socket connection
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    log_msg(f"Socket connection confirmed on port {port}")
                    return True
        except Exception:
            pass

        time.sleep(0.15)
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
        err_detail = server_error or f"Timeout after 35s waiting for server on port {port}."
        log_err(f"[CRITICAL ERROR] {err_detail}")
        show_error_dialog(
            "LKCS Exam Studio - Startup Error",
            f"The application backend could not start on port {port}.\n\nPlease check 'lkcs_desktop.log' located at:\n{LOG_FILE}",
            error_details=err_detail
        )
        return

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
