"""Release tags must identify the backend and cached card modules being shipped."""
import unittest
from scripts.check_release import check


class ReleaseTests(unittest.TestCase):
    def test_current_release_is_consistent(self):
        version = check()
        self.assertEqual(check('v'+version), version)

    def test_wrong_tag_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'tag'):
            check('v0.0.0-wrong')
