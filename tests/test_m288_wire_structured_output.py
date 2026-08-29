import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.errors import PlanningError
from agent.llm_planner import OpenAIPlannerClient
from agent.openai_config import load_openai_config
from agent.provider_structured_output import (
    build_structured_output_profile,
    project_structured_output_profile,
)


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return False

    def read(self):
        return self._payload


class M288WireStructuredOutputTests(unittest.TestCase):
    def test_config_defaults_to_strict_schema_and_explicit_object_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openai.local.json"
            path.write_text(json.dumps({"OPENAI_API_KEY": "sk-test"}), encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                default = load_openai_config(str(path))
            path.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "sk-test",
                        "structured_output_mode": "json_object",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                compatibility = load_openai_config(str(path))

        self.assertEqual(default["structured_output_mode"], "json_schema")
        self.assertEqual(compatibility["structured_output_mode"], "json_object")
        self.assertTrue(
            build_structured_output_profile(
                wire_api="chat_completions", structured_mode="json_schema"
            )["schema_enforced"]
        )
        self.assertFalse(
            build_structured_output_profile(
                wire_api="chat_completions", structured_mode="json_object"
            )["schema_enforced"]
        )

    def test_chat_request_uses_strict_schema_by_default(self):
        # The production relay intentionally uses json_object.  Isolate that
        # container setting so this unit test verifies the client default.
        with patch.dict(os.environ, {"OPENAI_STRUCTURED_OUTPUT_MODE": ""}):
            client = OpenAIPlannerClient(
                api_key="sk-test",
                model="deepseek-v4-flash",
                base_url="https://gateway.example",
                wire_api="chat_completions",
            )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            return_value=_Response(
                {"choices": [{"message": {"content": '{"goal":"ok"}'}}]}
            ),
        ) as urlopen:
            self.assertEqual(client.complete_json([], {"type": "object"}), {"goal": "ok"})

        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])

    def test_explicit_json_object_mode_is_wire_compatible_but_not_schema_authority(self):
        client = OpenAIPlannerClient(
            api_key="sk-test",
            base_url="https://gateway.example",
            wire_api="chat_completions",
            structured_output_mode="json_object",
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            return_value=_Response(
                {"choices": [{"message": {"content": '{"goal":"ok"}'}}]}
            ),
        ) as urlopen:
            client.complete_json([], {"type": "object"})

        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(client.metrics()["structured_mode"], "json_object")
        self.assertFalse(client.metrics()["schema_enforced"])

    def test_unavailable_mode_fails_closed_before_transport(self):
        client = OpenAIPlannerClient(
            api_key="sk-test",
            wire_api="chat_completions",
            structured_output_mode="unavailable",
        )
        with patch("agent.llm_planner.urllib.request.urlopen") as urlopen:
            with self.assertRaises(PlanningError):
                client.complete_json([], {})
        urlopen.assert_not_called()

    def test_profile_projection_is_bounded_and_never_contains_secret(self):
        profile = project_structured_output_profile(
            {
                "wire_api": "chat_completions",
                "structured_mode": "json_schema",
                "source": "config",
                "reason_code": "configured",
                "api_key": "sk-secret",
            }
        )
        self.assertEqual(profile["schema_version"], "spatial-agent.provider-structured-output.v1")
        self.assertNotIn("api_key", profile)
        self.assertNotIn("sk-secret", repr(profile))


if __name__ == "__main__":
    unittest.main()
