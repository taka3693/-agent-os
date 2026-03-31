"""Tests for multimodal system."""
import unittest
import tempfile
from pathlib import Path

from ops.multimodal_input import detect_input_type, SUPPORTED_FORMATS
from ops.output_generator import generate_mermaid_flowchart, generate_ascii_chart


class TestMultimodalInput(unittest.TestCase):
    def test_detect_text(self):
        result = detect_input_type("hello world")
        self.assertEqual(result["type"], "text")
    
    def test_detect_base64_image(self):
        result = detect_input_type("data:image/png;base64,abc123")
        self.assertEqual(result["type"], "image")
    
    def test_supported_formats(self):
        self.assertIn(".png", SUPPORTED_FORMATS["image"])
        self.assertIn(".pdf", SUPPORTED_FORMATS["document"])


class TestOutputGenerator(unittest.TestCase):
    def test_flowchart(self):
        result = generate_mermaid_flowchart(
            "Test",
            [{"id": "A", "label": "Start"}],
            [{"from": "A", "to": "B"}],
        )
        self.assertTrue(result["ok"])
        self.assertIn("flowchart TD", result["code"])
    
    def test_ascii_chart(self):
        result = generate_ascii_chart(
            "Test",
            [{"label": "A", "value": 50}, {"label": "B", "value": 100}],
        )
        self.assertTrue(result["ok"])
        self.assertIn("A", result["chart"])


if __name__ == "__main__":
    unittest.main()
