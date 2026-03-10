import unittest

from tools.lib.json_batch_parser import parse_json_batch_request


class Step89JsonBatchParserTests(unittest.TestCase):
    def test_non_json_batch_passthrough(self):
        matched, parsed, err = parse_json_batch_request("aos ls workspace")
        self.assertFalse(matched)
        self.assertIsNone(parsed)
        self.assertIsNone(err)

    def test_empty_json_batch(self):
        matched, parsed, err = parse_json_batch_request("aos json ")
        self.assertTrue(matched)
        self.assertIsNone(parsed)
        self.assertIsInstance(err, dict)
        self.assertFalse(err["ok"])
        self.assertTrue(err["is_json_batch"])

    def test_invalid_json(self):
        matched, parsed, err = parse_json_batch_request('aos json {"steps":')
        self.assertTrue(matched)
        self.assertIsNone(parsed)
        self.assertIsInstance(err, dict)
        self.assertIn("JSON 解析エラー", err["reply_text"])

    def test_empty_steps(self):
        matched, parsed, err = parse_json_batch_request('aos json {"steps":[]}')
        self.assertTrue(matched)
        self.assertIsNone(parsed)
        self.assertIsInstance(err, dict)
        self.assertIn("steps が空", err["reply_text"])

    def test_valid_request(self):
        matched, parsed, err = parse_json_batch_request(
            'aos json {"steps":["aos ls workspace"],"validate_only":true}'
        )
        self.assertTrue(matched)
        self.assertIsNone(err)
        self.assertEqual(parsed["steps"], ["aos ls workspace"])
        self.assertTrue(parsed["validate_only"])


if __name__ == "__main__":
    unittest.main()
