import unittest
import uuid

from knowledge_base_api.sync import stable_point_id


class SyncTests(unittest.TestCase):
    def test_stable_point_id_returns_uuid(self):
        point_id = stable_point_id("Meeting/2026/Meeting Index.md", "chunk-1")
        parsed = uuid.UUID(point_id)
        self.assertEqual(str(parsed), point_id)
        self.assertEqual(point_id, stable_point_id("Meeting/2026/Meeting Index.md", "chunk-1"))
