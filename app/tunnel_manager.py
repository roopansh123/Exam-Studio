import subprocess
import threading
import time
import re
import os
import shutil

import sys

def get_augmented_env():
    """Builds an environment dictionary with all possible Node/npx directories included in PATH."""
    env = os.environ.copy()
    current_path = env.get("PATH", "")
    
    additional_paths = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    
    # Check for user NVM installations on macOS / Linux
    home = os.path.expanduser("~")
    nvm_dir = os.path.join(home, ".nvm", "versions", "node")
    if os.path.exists(nvm_dir):
        try:
            for ver in os.listdir(nvm_dir):
                ver_bin = os.path.join(nvm_dir, ver, "bin")
                if os.path.isdir(ver_bin):
                    additional_paths.insert(0, ver_bin)
        except Exception:
            pass

    # Windows node paths
    if sys.platform == "win32":
        win_paths = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "nodejs"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "nodejs"),
            os.path.join(os.environ.get("APPDATA", ""), "npm"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "node"),
        ]
        additional_paths.extend([p for p in win_paths if p and os.path.exists(p)])

    path_sep = ";" if sys.platform == "win32" else ":"
    existing_list = current_path.split(path_sep) if current_path else []
    for p in additional_paths:
        if os.path.exists(p) and p not in existing_list:
            existing_list.insert(0, p)

    env["PATH"] = path_sep.join(existing_list)
    return env

class TunnelManager:
    _instance = None

    def __init__(self):
        self.process = None
        self.tunnel_url = None
        self.status = "stopped" # 'stopped', 'starting', 'running', 'error'
        self.error_message = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_tunnel(self, port=8000, subdomain=None):
        with self._lock:
            if self.process and self.process.poll() is None:
                return {"status": "already_running", "url": self.tunnel_url}

            env = get_augmented_env()
            npx_path = shutil.which("npx", path=env["PATH"])
            if not npx_path:
                for candidate in ["/opt/homebrew/bin/npx", "/usr/local/bin/npx", "npx.cmd", "npx"]:
                    if os.path.exists(candidate):
                        npx_path = candidate
                        break

            if not npx_path:
                self.status = "error"
                self.error_message = "Node/npx not found on system path. Please ensure Node.js is installed."
                return {"status": "error", "message": self.error_message}

            cmd = [npx_path, "--yes", "localtunnel", "--port", str(port)]
            if subdomain:
                cmd.extend(["--subdomain", subdomain])

            try:
                self.status = "starting"
                self.error_message = None
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env
                )
            except Exception as e:
                self.status = "error"
                self.error_message = str(e)
                return {"status": "error", "message": str(e)}

        # Reader thread to extract public URL
        def _read_output():
            url_pattern = re.compile(r"your url is:\s*(https?://[^\s]+)", re.IGNORECASE)
            for line in self.process.stdout:
                match = url_pattern.search(line)
                if match:
                    self.tunnel_url = match.group(1).strip()
                    self.status = "running"
                    break
            
            # Keep monitoring
            self.process.wait()
            with self._lock:
                self.status = "stopped"
                self.tunnel_url = None

        thread = threading.Thread(target=_read_output, daemon=True)
        thread.start()

        # Wait up to 8 seconds for URL
        for _ in range(25):
            if self.tunnel_url:
                return {"status": "running", "url": self.tunnel_url}
            if self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                self.status = "error"
                self.error_message = stderr or "Tunnel process exited unexpectedly."
                return {"status": "error", "message": self.error_message}
            time.sleep(0.3)

        if self.tunnel_url:
            return {"status": "running", "url": self.tunnel_url}
        else:
            return {"status": "starting", "url": None, "message": "Tunnel is initializing in background."}

    def stop_tunnel(self):
        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except Exception:
                    self.process.kill()
            self.process = None
            self.tunnel_url = None
            self.status = "stopped"
            return {"status": "stopped"}

    def get_status(self):
        is_running = bool(self.process and self.process.poll() is None and self.tunnel_url)
        return {
            "status": "running" if is_running else self.status,
            "url": self.tunnel_url if is_running else None,
            "error": self.error_message
        }
