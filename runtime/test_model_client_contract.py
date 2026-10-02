"""Contract tests use invented interface strings, never diagnostic cases."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_client


class ClientContract(unittest.TestCase):
    def run_reply(self, content, finish_reason="stop"):
        body = json.dumps({"model": "nengzhihe-qwen3-4b-q4km", "choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}).encode()
        with patch.object(model_client.urllib.request, "build_opener") as mock:
            mock.return_value.open.return_value = io.BytesIO(body)
            result = model_client.choose_action({"evidence": []}, ["query", "stop"])
        return result

    def test_allowed_reply(self):
        result = self.run_reply('{"action":"query","reason":"Need evidence."}')
        self.assertTrue(result["response_valid"])
        self.assertEqual(result["action"], "query")

    def test_forbidden_action(self):
        result = self.run_reply('{"action":"shell","reason":"Invalid action."}')
        self.assertFalse(result["response_valid"])
        self.assertIsNone(result["action"])

    def test_malformed_json(self):
        result = self.run_reply('```json\n{"action":"query","reason":"x"}\n```')
        self.assertFalse(result["response_valid"])
        self.assertIsNone(result["action"])

    def test_truncation(self):
        result = self.run_reply('{"action":"query","reason":"x"}', "length")
        self.assertFalse(result["response_valid"])
        self.assertIsNone(result["action"])

    def test_extra_keys(self):
        result = self.run_reply('{"action":"query","reason":"x","invented_measurement":123}')
        self.assertFalse(result["response_valid"])
        self.assertIsNone(result["action"])

    def test_empty_pool_never_calls_service(self):
        with patch.object(model_client.urllib.request, "build_opener") as mock:
            result = model_client.choose_action({}, [])
            mock.assert_not_called()
        self.assertFalse(result["response_valid"])

    def test_remote_userinfo_url_never_calls_service(self):
        config = json.loads(model_client.CONFIG_PATH.read_text(encoding="utf-8-sig"))
        config["base_url"] = "http://localhost:18191@example.com/v1"
        with patch.object(Path, "read_text", return_value=json.dumps(config)), patch.object(model_client.urllib.request, "build_opener") as mock:
            result = model_client.choose_action({}, ["stop"])
            mock.assert_not_called()
        self.assertFalse(result["response_valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
