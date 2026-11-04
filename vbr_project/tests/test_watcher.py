import tempfile
import time
import unittest
from pathlib import Path

from vbr.db import connect
from vbr.watcher import FolderWatcher


class WatcherTests(unittest.TestCase):
    def test_stable_file_is_imported_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "game.sqlite3"
            data_dir = root / "data"
            data_dir.mkdir()
            data_file = data_dir / "sample.K"
            data_file.write_text("STARTK\\n", encoding="ascii")

            main_conn = connect(db_path)
            watcher = FolderWatcher(db_path, data_dir, interval=0.25).start()
            try:
                deadline = time.monotonic() + 4
                row = None
                while time.monotonic() < deadline:
                    row = main_conn.execute(
                        "SELECT path, size FROM imported_files"
                    ).fetchone()
                    if row:
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(row)
                self.assertEqual(row["path"], str(data_file.resolve()))
                self.assertEqual(row["size"], data_file.stat().st_size)
                self.assertEqual(main_conn.execute("SELECT COUNT(*) FROM races").fetchone()[0], 0)
            finally:
                watcher.stop()
                main_conn.close()


if __name__ == "__main__":
    unittest.main()
