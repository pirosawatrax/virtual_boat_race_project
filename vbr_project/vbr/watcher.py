"""Background folder watcher for automatically importing race data files."""
from pathlib import Path
import sqlite3
import threading
import time

from .db import connect
from .importers import import_file


class FolderWatcher:
    """Import stable files dropped into a folder, using a separate DB connection.

    A file must have the same size and modification time for two scans before
    it is imported. This avoids reading files while they are still being copied.
    """

    def __init__(self, db_path, folder="data", interval=1.0):
        self.db_path = str(db_path)
        self.folder = Path(folder).expanduser().resolve()
        self.interval = max(0.25, float(interval))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vbr-folder-watcher",
                                        daemon=True)

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self._thread.start()
        print(f"[watch] Monitoring {self.folder} for new data files")
        return self

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self):
        conn = None
        observed = {}
        attempted = set()
        try:
            conn = connect(self.db_path)
            while not self._stop.is_set():
                try:
                    self._scan(conn, observed, attempted)
                except Exception as exc:  # Keep the game alive if a scan fails.
                    print(f"[watch] Scan error: {exc}")
                self._stop.wait(self.interval)
        finally:
            if conn is not None:
                conn.close()

    def _scan(self, conn, observed, attempted):
        current = set()
        for path in self.folder.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            signature = (stat.st_size, stat.st_mtime_ns)
            key = str(path.resolve())
            current.add(key)
            previous = observed.get(key)
            if previous is None or previous[0] != signature:
                observed[key] = (signature, 1)
                continue
            observed[key] = (signature, previous[1] + 1)
            if observed[key][1] < 2 or (key, signature) in attempted:
                continue

            saved = conn.execute(
                "SELECT size, mtime_ns FROM imported_files WHERE path=?", (key,)
            ).fetchone()
            if saved and (saved["size"], saved["mtime_ns"]) == signature:
                attempted.add((key, signature))
                continue

            try:
                report = import_file(conn, path)
                detail = ", ".join(
                    f"{name}={value}" for name, value in report.items()
                    if name not in ("kind", "anomalies")
                )
                conn.execute(
                    "INSERT INTO imported_files(path,size,mtime_ns,imported_at) "
                    "VALUES(?,?,?,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(path) DO UPDATE SET size=excluded.size, "
                    "mtime_ns=excluded.mtime_ns, imported_at=CURRENT_TIMESTAMP",
                    (key, *signature),
                )
                conn.commit()
                attempted.add((key, signature))
                print(f"\n[watch] Imported {path.name}: {report['kind']} {detail}")
                for anomaly in report.get("anomalies", [])[:5]:
                    print(f"[watch] ! {anomaly[:180]}")
                extra = len(report.get("anomalies", [])) - 5
                if extra > 0:
                    print(f"[watch] ! ... and {extra} more anomalies")
            except (OSError, ValueError) as exc:
                attempted.add((key, signature))
                print(f"\n[watch] Skipped {path.name}: {exc}")
            except sqlite3.OperationalError as exc:
                # A transient database lock should be retried on the next scan.
                print(f"\n[watch] Database busy for {path.name}; will retry: {exc}")

        # Forget files that have been removed so re-adding them is detected.
        for key in list(observed):
            if key not in current:
                observed.pop(key, None)
        attempted.intersection_update(
            (key, observed[key][0]) for key in observed
        )
