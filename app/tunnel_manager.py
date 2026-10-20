import subprocess
import threading
import time
import re
import os
import shutil
import sys
import platform
import logging
import urllib.request
import ssl
import tarfile

logger = logging.getLogger("LKCS-Tunnel")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [Tunnel] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def get_augmented_env():
    """Builds an environment dictionary with all possible Node/npx/ssh/cloudflared directories included in PATH."""
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

    # Windows paths
    if sys.platform == "win32":
        win_paths = [
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH"),
            r"C:\Windows\System32\OpenSSH",
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "nodejs"),
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "cloudflared"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "cloudflared"),
            os.path.join(os.environ.get("APPDATA", ""), "npm"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "node"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "cloudflared"),
        ]
        additional_paths.extend([p for p in win_paths if p and os.path.exists(p)])

    # Also add ~/.lkcs/bin
    lkcs_bin = os.path.join(home, ".lkcs", "bin")
    if os.path.exists(lkcs_bin):
        additional_paths.insert(0, lkcs_bin)

    path_sep = ";" if sys.platform == "win32" else ":"
    existing_list = current_path.split(path_sep) if current_path else []
    for p in additional_paths:
        if os.path.exists(p) and p not in existing_list:
            existing_list.insert(0, p)

    env["PATH"] = path_sep.join(existing_list)
    return env

def make_executable(path):
    """Ensure binary has execute permissions on Unix."""
    if sys.platform != "win32" and os.path.exists(path):
        try:
            current_mode = os.stat(path).st_mode
            os.chmod(path, current_mode | 0o755)
        except Exception as e:
            logger.debug(f"chmod failed on {path}: {e}")

def get_cloudflared_binary(env):
    """Locate existing cloudflared binary across bundle, app/bin, user home cache, PATH, or system dirs."""
    bin_name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"

    # 1. PyInstaller frozen bundle path (_MEIPASS)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_bin = os.path.join(sys._MEIPASS, "app", "bin", bin_name)
        if os.path.exists(bundle_bin):
            make_executable(bundle_bin)
            return bundle_bin

    # 2. Local project app/bin directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_bin = os.path.join(base_dir, "bin", bin_name)
    if os.path.exists(local_bin):
        make_executable(local_bin)
        return local_bin

    # 3. User home cache directory (~/.lkcs/bin/)
    home_bin = os.path.join(os.path.expanduser("~"), ".lkcs", "bin", bin_name)
    if os.path.exists(home_bin):
        make_executable(home_bin)
        return home_bin

    # 4. PATH search
    found = shutil.which(bin_name, path=env.get("PATH"))
    if found:
        make_executable(found)
        return found

    # 5. Common OS directories
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "cloudflared", "cloudflared.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "cloudflared", "cloudflared.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "cloudflared", "cloudflared.exe"),
            r"C:\cloudflared\cloudflared.exe",
            r"C:\Windows\System32\cloudflared.exe",
        ]
    else:
        candidates = [
            "/opt/homebrew/bin/cloudflared",
            "/usr/local/bin/cloudflared",
            "/usr/bin/cloudflared",
            "/bin/cloudflared",
        ]
    for c in candidates:
        if c and os.path.exists(c):
            make_executable(c)
            return c

    return None

def download_cloudflared_if_needed(env):
    """Downloads standalone cloudflared binary into ~/.lkcs/bin if not already present."""
    existing = get_cloudflared_binary(env)
    if existing:
        return existing

    bin_name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
    target_dir = os.path.join(os.path.expanduser("~"), ".lkcs", "bin")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, bin_name)

    logger.info(f"cloudflared not found locally. Attempting automatic download to {target_path}...")

    # Determine URL
    download_url = None
    is_archive = False
    arch = platform.machine().lower()

    if sys.platform == "win32":
        download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    elif sys.platform == "darwin":
        is_archive = True
        if "arm" in arch or "aarch64" in arch:
            download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz"
        else:
            download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"
    elif sys.platform.startswith("linux"):
        if "arm" in arch or "aarch64" in arch:
            download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        else:
            download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

    if not download_url:
        return None

    try:
        # Create SSL context with fallback for systems with missing CA bundles
        try:
            ctx = ssl.create_default_context()
        except Exception:
            ctx = ssl._create_unverified_context()

        req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0 (LKCS-Exam-Studio)"})
        
        try:
            resp = urllib.request.urlopen(req, context=ctx, timeout=20)
        except ssl.SSLError:
            ctx = ssl._create_unverified_context()
            resp = urllib.request.urlopen(req, context=ctx, timeout=20)

        if is_archive:
            archive_path = target_path + ".tgz"
            with open(archive_path, "wb") as f:
                shutil.copyfileobj(resp, f)
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=target_dir)
            try:
                os.remove(archive_path)
            except Exception:
                pass
        else:
            with open(target_path, "wb") as f:
                shutil.copyfileobj(resp, f)

        if os.path.exists(target_path):
            make_executable(target_path)
            logger.info(f"cloudflared successfully downloaded to {target_path}")
            return target_path
    except Exception as e:
        logger.warning(f"Could not auto-download cloudflared: {e}. Will fall back to SSH/OpenSSH tunnel.")
        return None

    return None

def get_ssh_binary(env):
    bin_name = "ssh.exe" if sys.platform == "win32" else "ssh"
    found = shutil.which(bin_name, path=env.get("PATH"))
    if found:
        return found
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe"),
            r"C:\Windows\System32\OpenSSH\ssh.exe",
        ]
    else:
        candidates = ["/usr/bin/ssh", "/usr/local/bin/ssh", "/opt/homebrew/bin/ssh"]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def get_npx_binary(env):
    found = shutil.which("npx", path=env.get("PATH"))
    if found:
        return found
    for candidate in ["/opt/homebrew/bin/npx", "/usr/local/bin/npx", "npx.cmd", "npx"]:
        if os.path.exists(candidate):
            return candidate
    return None


class TunnelManager:
    _instance = None

    def __init__(self):
        self.process = None
        self.tunnel_url = None
        self.provider = None          # 'cloudflare', 'localhost.run', 'localtunnel'
        self.status = "stopped"       # 'stopped', 'starting', 'running', 'reconnecting', 'error'
        self.error_message = None
        self.port = 8000
        self.subdomain = None
        
        self.reconnect_count = 0
        self.last_reconnect_time = None
        
        self._should_run = False
        self._lock = threading.RLock()
        self._supervisor_thread = None
        self._heartbeat_thread = None
        self._url_callbacks = []

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_url_change_callback(self, callback):
        """Register a callback fn(new_url, provider) triggered whenever tunnel URL starts or changes."""
        with self._lock:
            if callback not in self._url_callbacks:
                self._url_callbacks.append(callback)

    def _notify_callbacks(self, new_url, provider):
        """Notify all callbacks that a new tunnel URL is active."""
        if not new_url:
            return
        with self._lock:
            callbacks = list(self._url_callbacks)
        for cb in callbacks:
            try:
                cb(new_url, provider)
            except Exception as e:
                logger.error(f"Error in tunnel URL change callback: {e}")

    def _spawn_process(self, cmd, env):
        """Starts subprocess with NO_WINDOW on Windows and unified stdout/stderr."""
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
            "env": env
        }
        if sys.platform == "win32":
            # Avoid showing console window on Windows
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        return subprocess.Popen(cmd, **kwargs)

    def _launch_tunnel_process(self):
        """Selects provider (Cloudflare > OpenSSH > localtunnel) and starts process."""
        env = get_augmented_env()
        
        # 1. Try Cloudflare Quick Tunnel (Primary - Unlimited session, high reliability)
        cf_bin = get_cloudflared_binary(env)
        if not cf_bin:
            cf_bin = download_cloudflared_if_needed(env)
            
        if cf_bin:
            cmd = [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"]
            try:
                logger.info(f"Launching Cloudflare Quick Tunnel using: {cf_bin}")
                proc = self._spawn_process(cmd, env)
                return proc, "cloudflare"
            except Exception as e:
                logger.warning(f"Failed to spawn cloudflared: {e}. Falling back to OpenSSH...")

        # 2. Try OpenSSH (localhost.run) with persistent keep-alive flags
        ssh_bin = get_ssh_binary(env)
        if ssh_bin:
            cmd = [
                ssh_bin,
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=120",
                "-o", "TCPKeepAlive=yes",
                "-o", "ExitOnForwardFailure=yes",
                "-R", f"80:localhost:{self.port}",
                "nokey@localhost.run"
            ]
            try:
                logger.info(f"Launching OpenSSH reverse tunnel using: {ssh_bin}")
                proc = self._spawn_process(cmd, env)
                return proc, "localhost.run"
            except Exception as e:
                logger.warning(f"Failed to spawn ssh: {e}. Falling back to localtunnel...")

        # 3. Try npx localtunnel
        npx_bin = get_npx_binary(env)
        if npx_bin:
            cmd = [npx_bin, "--yes", "localtunnel", "--port", str(self.port)]
            if self.subdomain:
                cmd.extend(["--subdomain", self.subdomain])
            try:
                logger.info(f"Launching localtunnel using: {npx_bin}")
                proc = self._spawn_process(cmd, env)
                return proc, "localtunnel"
            except Exception as e:
                logger.error(f"Failed to spawn npx localtunnel: {e}")

        return None, None

    def _ensure_heartbeat_running(self):
        """Starts background heartbeat sender to keep intermediate NAT / stateful firewalls alive."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        def _heartbeat_worker():
            logger.info("Tunnel keep-alive heartbeat worker started.")
            while self._should_run:
                # Ping every 25 seconds
                for _ in range(25):
                    if not self._should_run:
                        break
                    time.sleep(1)

                if not self._should_run:
                    break

                current_url = self.tunnel_url
                if current_url and self.status == "running":
                    try:
                        ping_url = f"{current_url.rstrip('/')}/api/tunnel/heartbeat"
                        req = urllib.request.Request(
                            ping_url,
                            headers={"User-Agent": "LKCS-Tunnel-Heartbeat/1.0"}
                        )
                        # Silent fast ping
                        try:
                            ctx = ssl.create_default_context()
                        except Exception:
                            ctx = ssl._create_unverified_context()

                        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                            _ = resp.read()
                    except Exception as ex:
                        logger.debug(f"Tunnel heartbeat ping quiet fail (normal during reconnect): {ex}")

            logger.info("Tunnel keep-alive heartbeat worker stopped.")

        self._heartbeat_thread = threading.Thread(target=_heartbeat_worker, daemon=True, name="LKCS-TunnelHeartbeat")
        self._heartbeat_thread.start()

    def _supervisor_loop(self):
        """Watchdog supervisor loop that keeps the tunnel alive 24/7 with auto-reconnection."""
        logger.info("Tunnel supervisor watchdog loop started.")

        cf_url_pattern = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", re.IGNORECASE)
        general_url_pattern = re.compile(r"https?://[a-zA-Z0-9.-]+\.(?:loca\.lt|lhr\.life|localhost\.run)[^\s]*", re.IGNORECASE)
        any_url_pattern = re.compile(r"https://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*", re.IGNORECASE)

        while self._should_run:
            proc, provider = self._launch_tunnel_process()
            if not proc:
                with self._lock:
                    self.status = "error"
                    self.error_message = "No tunneling utility (cloudflared, ssh, npx) is available on this system."
                logger.error(self.error_message)
                time.sleep(5)
                continue

            with self._lock:
                self.process = proc
                self.provider = provider
                self.status = "starting"
                self.error_message = None

            # Reader loop to parse lines and extract URL
            found_url = None
            start_wait = time.time()

            while self._should_run and proc.poll() is None:
                # Read line with timeout via non-blocking or simple readline
                line = proc.stdout.readline()
                if not line:
                    break

                line_str = line.strip()
                if line_str:
                    logger.debug(f"[{provider}] {line_str}")

                # Pattern matching
                match = None
                if provider == "cloudflare":
                    match = cf_url_pattern.search(line_str)
                else:
                    match = general_url_pattern.search(line_str)
                    if not match and ("your url is" in line_str.lower() or "tunneled with tls" in line_str.lower()):
                        match = any_url_pattern.search(line_str)

                if match:
                    found_url = match.group(0).rstrip(",;.")
                    with self._lock:
                        self.tunnel_url = found_url
                        self.status = "running"
                    logger.info(f"Tunnel successfully established! URL: {found_url} (provider: {provider})")
                    self._notify_callbacks(found_url, provider)
                    self._ensure_heartbeat_running()
                    break

                # If 15 seconds passed without URL, break to check status
                if not found_url and (time.time() - start_wait > 15):
                    logger.warning("Tunnel initialization took over 15s without emitting URL. Waiting for process...")
                    break

            # Now continue reading stdout until process ends to prevent pipe buffer stalling
            while self._should_run and proc.poll() is None:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.5)

            # Process exited or was killed
            exit_code = proc.poll()
            logger.warning(f"Tunnel process ({provider}) exited with code {exit_code}.")

            if not self._should_run:
                logger.info("Supervisor loop terminating (user requested stop).")
                break

            # If user wanted it running, handle automatic reconnect!
            with self._lock:
                self.status = "reconnecting"
                self.tunnel_url = None
                self.reconnect_count += 1
                self.last_reconnect_time = time.time()

            logger.info(f"Watchdog auto-reconnecting tunnel in 3 seconds (reconnect attempt #{self.reconnect_count})...")
            time.sleep(3)

        with self._lock:
            self.status = "stopped"
            self.tunnel_url = None
            self.process = None

        logger.info("Tunnel supervisor watchdog loop finished.")

    def start_tunnel(self, port=8000, subdomain=None):
        """Starts the internet tunnel and supervisor watchdog."""
        with self._lock:
            self.port = port
            self.subdomain = subdomain

            if self.status == "running" and self.process and self.process.poll() is None and self.tunnel_url:
                return {
                    "status": "running",
                    "url": self.tunnel_url,
                    "provider": self.provider
                }

            self._should_run = True
            self.status = "starting"
            self.error_message = None

            # Start supervisor thread if not running
            if not self._supervisor_thread or not self._supervisor_thread.is_alive():
                self._supervisor_thread = threading.Thread(
                    target=self._supervisor_loop,
                    daemon=True,
                    name="LKCS-TunnelSupervisor"
                )
                self._supervisor_thread.start()

        # Wait up to 12 seconds for the URL to become available
        for _ in range(48):
            with self._lock:
                if self.status == "running" and self.tunnel_url:
                    return {
                        "status": "running",
                        "url": self.tunnel_url,
                        "provider": self.provider
                    }
                if self.status == "error":
                    return {
                        "status": "error",
                        "message": self.error_message or "Tunnel startup failed."
                    }
            time.sleep(0.25)

        with self._lock:
            if self.tunnel_url:
                return {"status": "running", "url": self.tunnel_url, "provider": self.provider}
            return {
                "status": self.status,
                "url": self.tunnel_url,
                "provider": self.provider,
                "message": "Tunnel is starting in the background. It will be available in a few seconds."
            }

    def stop_tunnel(self):
        """Stops the internet tunnel and terminates background workers."""
        with self._lock:
            self._should_run = False
            proc = self.process
            self.process = None
            self.tunnel_url = None
            self.status = "stopped"

        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        return {"status": "stopped"}

    def get_status(self):
        """Returns the current real-time health and details of the tunnel."""
        with self._lock:
            is_active = bool(
                self._should_run and
                self.process and
                self.process.poll() is None and
                self.tunnel_url and
                self.status == "running"
            )
            return {
                "status": "running" if is_active else self.status,
                "url": self.tunnel_url if is_active else None,
                "provider": self.provider if is_active else None,
                "reconnect_count": self.reconnect_count,
                "last_reconnect_time": self.last_reconnect_time,
                "error": self.error_message
            }
