"""
Coach Biruktawit Bot Dev Auto-Reloader
Watches project files (.py, .env) using mtime + content hash and automatically restarts bot.py on real changes.
Also auto-recovers if bot.py exits due to a transient network/DNS drop.
"""

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

WATCH_EXTENSIONS = {".py", ".env"}
WATCH_DIRS = [
    PROJECT_ROOT / "handlers",
    PROJECT_ROOT / "keyboards",
    PROJECT_ROOT / "services",
    PROJECT_ROOT / "database",
    PROJECT_ROOT / "scripts",
]
WATCH_FILES = [
    PROJECT_ROOT / "bot.py",
    PROJECT_ROOT / ".env",
]
IGNORE_DIRS = {"__pycache__", ".git", ".pytest_cache", ".venv", "logs", ".system_generated"}
IGNORE_FILES = {Path(__file__).resolve()}


def log(msg: str):
    """Print with immediate stdout flush for real-time terminal output."""
    print(msg, flush=True)


def _file_signature(path: Path) -> tuple[float, str] | None:
    try:
        mtime = path.stat().st_mtime
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        return (mtime, digest)
    except OSError:
        return None


def get_watched_files() -> dict[str, tuple[float, str]]:
    """Collect all watched files and their (mtime, md5) signatures."""
    files = {}

    for fpath in WATCH_FILES:
        if fpath.is_file() and fpath not in IGNORE_FILES:
            sig = _file_signature(fpath)
            if sig:
                files[str(fpath)] = sig

    for wdir in WATCH_DIRS:
        if not wdir.is_dir():
            continue
        for root, dirs, filenames in os.walk(wdir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in WATCH_EXTENSIONS or fname == ".env":
                    full_path = Path(root) / fname
                    if full_path not in IGNORE_FILES:
                        sig = _file_signature(full_path)
                        if sig:
                            files[str(full_path)] = sig

    return files


def terminate_process(proc):
    """Gracefully and completely kill the child process and its tree on Windows."""
    if proc is None or proc.poll() is not None:
        return

    pid = proc.pid
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass


def start_bot():
    """Start bot.py as a child subprocess with unbuffered output."""
    log("=" * 60)
    log(" [WATCHER] Launching bot.py...")
    log("=" * 60)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "bot.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
    )


def main():
    log("========================================================")
    log(" BIRUKTAWIT BOT AUTO-RELOAD ENGINE ACTIVE")
    log(f" Watching: .py, .env in {PROJECT_ROOT.name}")
    log(" Press Ctrl+C to stop.")
    log("========================================================\n")

    current_snapshot = get_watched_files()
    proc = start_bot()
    last_crash_retry = 0.0

    try:
        while True:
            time.sleep(0.8)
            latest_snapshot = get_watched_files()

            changed_file = None

            for path, (_, old_hash) in current_snapshot.items():
                if path not in latest_snapshot:
                    changed_file = f"(deleted) {Path(path).name}"
                    break
                if old_hash != latest_snapshot[path][1]:
                    try:
                        rel = Path(path).relative_to(PROJECT_ROOT)
                    except ValueError:
                        rel = Path(path).name
                    changed_file = str(rel)
                    break

            if not changed_file:
                for path in latest_snapshot:
                    if path not in current_snapshot:
                        try:
                            rel = Path(path).relative_to(PROJECT_ROOT)
                        except ValueError:
                            rel = Path(path).name
                        changed_file = f"(new) {rel}"
                        break

            # Sync timestamps even if hash didn't change
            current_snapshot = latest_snapshot

            if changed_file:
                time.sleep(0.3)
                current_snapshot = get_watched_files()

                log("\n" + "-" * 60)
                log(f" [WATCHER] Change detected in: {changed_file}")
                log(" [WATCHER] Restarting bot engine...")
                log("-" * 60)

                terminate_process(proc)
                time.sleep(0.5)
                proc = start_bot()
                last_crash_retry = time.time()
            elif proc and proc.poll() is not None:
                now = time.time()
                if now - last_crash_retry >= 5.0:
                    log(f"\n[WATCHER] bot.py exited (code {proc.returncode}). Retrying in 5s...")
                    last_crash_retry = now
                    time.sleep(5.0)
                    proc = start_bot()

    except KeyboardInterrupt:
        log("\n[WATCHER] Stopping bot...")
        terminate_process(proc)
        log("[WATCHER] Clean shutdown complete.")


if __name__ == "__main__":
    main()
