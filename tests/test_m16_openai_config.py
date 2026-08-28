import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.errors import PlanningError
from agent.llm_planner import (
    LLMPlanner,
    OpenAIPlannerClient,
    _append_query_param,
    _chat_completions_url,
    _planner_url,
    _responses_url,
)
from agent.openai_config import load_answer_generation_config, load_openai_config
from run_demo import build_runtime


class M16OpenAIConfigTests(unittest.TestCase):
    def test_loads_local_json_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openai.local.json"
            path.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "sk-test",
                        "model": "gpt-5.6-luna",
                        "wire_api": "responses",
                        "max_output_tokens": 10000,
                        "timeout_seconds": 45,
                        "model_reasoning_effort": "medium",
                        "api_url": "https://crs.ruinique.com/custom",
                        "base_url": "https://crs.ruinique.com",
                        "auth_location": "query",
                        "api_key_query_param": "api_key",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_openai_config(str(path))

        self.assertEqual(config["api_key"], "sk-test")
        self.assertEqual(config["model"], "gpt-5.6-luna")
        self.assertEqual(config["wire_api"], "responses")
        self.assertEqual(config["max_output_tokens"], 10000)
        self.assertEqual(config["timeout_seconds"], 45.0)
        self.assertEqual(config["reasoning_effort"], "medium")
        self.assertEqual(config["api_url"], "https://crs.ruinique.com/custom")
        self.assertEqual(config["base_url"], "https://crs.ruinique.com")
        self.assertEqual(config["auth_location"], "query")
        self.assertEqual(config["api_key_query_param"], "api_key")

    def test_environment_overrides_local_json_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openai.local.json"
            path.write_text(
                json.dumps({"OPENAI_API_KEY": "sk-file", "model": "file-model"}),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "sk-env", "OPENAI_MODEL": "env-model"},
                clear=True,
            ):
                config = load_openai_config(str(path))

        self.assertEqual(config["api_key"], "sk-env")
        self.assertEqual(config["model"], "env-model")

    def test_answer_generation_uses_a_separate_latency_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openai.local.json"
            path.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "sk-test",
                        "model": "answer-model",
                        "max_output_tokens": 4096,
                        "timeout_seconds": 45,
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_answer_generation_config(str(path))

        self.assertEqual(config["timeout_seconds"], 20.0)
        self.assertEqual(config["max_output_tokens"], 4096)
        self.assertEqual(config["max_retries"], 0)

    def test_answer_generation_budget_can_be_explicitly_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openai.local.json"
            path.write_text(json.dumps({"OPENAI_API_KEY": "sk-test"}), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "OPENAI_ANSWER_TIMEOUT_SECONDS": "9",
                    "OPENAI_ANSWER_MAX_OUTPUT_TOKENS": "320",
                    "OPENAI_ANSWER_MAX_RETRIES": "1",
                },
                clear=True,
            ):
                config = load_answer_generation_config(str(path))

        self.assertEqual(config["timeout_seconds"], 9.0)
        self.assertEqual(config["max_output_tokens"], 320)
        self.assertEqual(config["max_retries"], 1)

    def test_responses_url_accepts_provider_base_urls(self):
        self.assertEqual(_responses_url("https://crs.ruinique.com"), "https://crs.ruinique.com/v1/responses")
        self.assertEqual(_responses_url("https://crs.ruinique.com/v1"), "https://crs.ruinique.com/v1/responses")
        self.assertEqual(_responses_url("https://crs.ruinique.com/v1/responses"), "https://crs.ruinique.com/v1/responses")

    def test_explicit_api_url_is_used_without_v1_or_responses_suffix(self):
        self.assertEqual(
            _planner_url("https://crs.ruinique.com/direct", "https://ignored.example"),
            "https://crs.ruinique.com/direct",
        )

    def test_chat_completions_url_matches_deepseek_base_url(self):
        self.assertEqual(
            _chat_completions_url("https://api.deepseek.com"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            _chat_completions_url("https://api.deepseek.com/v1"),
            "https://api.deepseek.com/v1/chat/completions",
        )

    def test_openai_client_rejects_unknown_wire_api(self):
        with self.assertRaises(PlanningError):
            OpenAIPlannerClient(api_key="sk-test", wire_api="unknown")

    def test_chat_completions_extracts_message_content(self):
        client = OpenAIPlannerClient(
            api_key="sk-test",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            wire_api="chat_completions",
        )

        self.assertEqual(
            client._extract_text(
                {"choices": [{"message": {"content": '{"goal":"ok"}'}}]}
            ),
            '{"goal":"ok"}',
        )

    def test_query_auth_appends_key_without_replacing_existing_key(self):
        self.assertEqual(
            _append_query_param("https://crs.ruinique.com/direct?foo=bar", "key", "sk-test"),
            "https://crs.ruinique.com/direct?foo=bar&key=sk-test",
        )
        self.assertEqual(
            _append_query_param("https://crs.ruinique.com/direct?key=existing", "key", "sk-test"),
            "https://crs.ruinique.com/direct?key=existing",
        )

    def test_openai_client_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PlanningError):
                OpenAIPlannerClient(api_key=None)

    def test_openai_client_exposes_safe_metrics_defaults(self):
        client = OpenAIPlannerClient(
            api_key="sk-test",
            model="deepseek-v4-flash",
            wire_api="chat_completions",
            max_output_tokens=800,
            timeout_seconds=12,
        )

        self.assertEqual(client.metrics()["model"], "deepseek-v4-flash")
        self.assertEqual(client.metrics()["wire_api"], "chat_completions")
        self.assertNotIn("api_key", client.metrics())

    def test_chat_completions_sends_token_limit_and_records_usage(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [{"message": {"content": '{"goal":"ok"}'}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                    }
                ).encode("utf-8")

        client = OpenAIPlannerClient(
            api_key="sk-test",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            wire_api="chat_completions",
            max_output_tokens=800,
            timeout_seconds=12,
        )
        with patch("agent.llm_planner.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            payload = client.complete_json([], schema={})

        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload, {"goal": "ok"})
        self.assertEqual(body["max_tokens"], 800)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 12)
        self.assertEqual(client.metrics()["usage"]["total_tokens"], 14)

    def test_chat_completions_records_bounded_finish_reason(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "length",
                                "message": {"content": '{"goal":"'}
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 800, "total_tokens": 810},
                    }
                ).encode("utf-8")

        client = OpenAIPlannerClient(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            wire_api="chat_completions",
            max_output_tokens=800,
            max_retries=0,
        )
        with patch("agent.llm_planner.urllib.request.urlopen", return_value=FakeResponse()):
            with self.assertRaises(PlanningError) as raised:
                client.complete_json([], {})
        self.assertEqual(raised.exception.code, "invalid_model_response")
        self.assertEqual(client.metrics()["finish_reason"], "length")

    def test_compact_recovery_uses_larger_deterministic_budget(self):
        class FakeResponse:
            def __init__(self, content, finish_reason, completion_tokens):
                self._payload = json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": finish_reason,
                                "message": {"content": content},
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": completion_tokens,
                            "total_tokens": 10 + completion_tokens,
                        },
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return self._payload

        responses = [
            FakeResponse('{"goal":"', "length", 2048),
            FakeResponse(
                json.dumps(
                    {
                        "goal": "查询 DEM 元数据",
                        "steps": [
                            {
                                "id": "metadata",
                                "tool": "get_raster_metadata",
                                "args": {},
                            }
                        ],
                        "output": {"type": "raster_metadata_result"},
                    }
                ),
                "stop",
                180,
            ),
        ]
        client = OpenAIPlannerClient(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            wire_api="chat_completions",
            max_output_tokens=2048,
            max_retries=0,
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            side_effect=responses,
        ) as urlopen:
            plan = LLMPlanner(client, ["get_raster_metadata"]).plan("查询 DEM 元数据")

        self.assertEqual(plan.steps[0].tool, "get_raster_metadata")
        self.assertEqual(urlopen.call_count, 2)
        first_body = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        recovery_body = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(first_body["max_tokens"], 2048)
        self.assertEqual(recovery_body["max_tokens"], 4096)
        self.assertEqual(recovery_body["temperature"], 0)

    def test_invalid_model_response_gets_one_compact_plan_recovery(self):
        class RecoveryClient:
            def __init__(self):
                self.calls = []

            def complete_json(self, messages, _schema):
                self.calls.append(messages)
                if len(self.calls) == 1:
                    raise PlanningError(
                        "invalid JSON",
                        category="planning",
                        code="invalid_model_response",
                    )
                return {
                    "goal": "查询 DEM 元数据",
                    "steps": [{"id": "metadata", "tool": "get_raster_metadata", "args": {}}],
                    "output": {"type": "raster_metadata_result"},
                }

            def metrics(self):
                return {"status": "success"}

        client = RecoveryClient()
        planner = LLMPlanner(client, ["get_raster_metadata"])
        plan = planner.plan("查询 DEM 元数据")
        self.assertEqual(plan.steps[0].tool, "get_raster_metadata")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(planner.metrics()["compact_recovery_attempts"], 1)
        self.assertIn("exactly one compact JSON", client.calls[1][0]["content"])


@unittest.skipUnless(os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") == "1", "set SPATIAL_AGENT_LIVE_OPENAI=1 to run live OpenAI planner smoke")
class M16LiveOpenAIPlannerTests(unittest.TestCase):
    def test_live_openai_planner_generates_registered_tool_plan(self):
        result = build_runtime("openai", "memory").run("查询DEM栅格元数据")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertTrue(result.steps)
        self.assertEqual(result.steps[0].tool, "get_raster_metadata")


if __name__ == "__main__":
    unittest.main()
