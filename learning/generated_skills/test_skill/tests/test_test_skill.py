"""
Tests for test_skill skill
"""

import unittest
import sys
from pathlib import Path

# Add skills directory to path
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
sys.path.insert(0, str(SKILLS_DIR))


class TestTestskill(unittest.TestCase):
    """Test cases for test_skill skill"""

    def setUp(self):
        """Set up test fixtures"""
        from test_skill import get_skill
        self.skill = get_skill()

    def test_skill_initialization(self):
        """Test skill can be initialized"""
        self.assertIsNotNone(self.skill)
        self.assertEqual(self.skill.name, "test_skill")


    def test_get_capabilities(self):
        """Test get_capabilities returns expected list"""
        caps = self.skill.get_capabilities()
        self.assertIsInstance(caps, list)
        self.assertEqual(len(caps), 0)


if __name__ == "__main__":
    unittest.main()
