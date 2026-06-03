import unittest
from pathlib import Path

from hermes.store import Store


class StoreTests(unittest.TestCase):
    def test_store_create_and_get_task(self):
        tmp = Path(self._testMethodName).with_suffix(".db")
        if tmp.exists():
            tmp.unlink()
        store = Store(tmp)
        try:
            task = store.create_task(
                task_id="task_1",
                status="queued",
                source="api",
                event_type="merge",
                project_id="1",
                branch="main",
                commit_sha="abc",
                delivery_id="d1",
                trigger_reason="test",
            )
            got = store.get_task(task.task_id)
            self.assertIsNotNone(got)
            self.assertEqual(got.status, "queued")
        finally:
            store.close()
            if tmp.exists():
                tmp.unlink()
