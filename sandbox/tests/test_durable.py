import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sandbox import durable


class DurableTests(unittest.TestCase):
    def test_failed_replace_preserves_previous_record_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            durable.atomic_json(path, {"candidate": "old"})
            with patch.object(durable.os, "replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    durable.atomic_json(path, {"candidate": "new"})
            self.assertEqual(json.loads(path.read_bytes()), {"candidate": "old"})
            self.assertEqual([item.name for item in Path(temp).iterdir()], ["state.json"])

    def test_flush_failure_cannot_publish_unflushed_record(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            with patch.object(durable.os, "fsync", side_effect=OSError("disk failed")):
                with self.assertRaises(OSError):
                    durable.atomic_json(path, {"prepared": True})
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(temp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
