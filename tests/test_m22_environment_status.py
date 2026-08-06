import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.environment_status import environment_status


class M22EnvironmentStatusTests(unittest.TestCase):
    def test_live_llm_requires_config_and_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "openai.local.json"
            config.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "sk-test",
                        "base_url": "https://api.deepseek.com",
                        "wire_api": "chat_completions",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENAI_CONFIG_FILE": str(config)}, clear=True):
                with patch(
                    "agent.environment_status.socket.create_connection",
                    side_effect=OSError("socket denied"),
                ):
                    status = environment_status()

        self.assertIs(status["capabilities"]["live_llm_configured"], True)
        self.assertIs(status["capabilities"]["live_llm_network"], False)
        self.assertIs(status["capabilities"]["live_llm"], False)

    def test_live_llm_is_available_when_configured_host_accepts_socket(self):
        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "openai.local.json"
            config.write_text(
                json.dumps({"OPENAI_API_KEY": "sk-test", "base_url": "https://api.deepseek.com"}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENAI_CONFIG_FILE": str(config)}, clear=True):
                with patch(
                    "agent.environment_status.socket.create_connection",
                    return_value=FakeSocket(),
                ) as create_connection:
                    status = environment_status()

        create_connection.assert_called_once_with(("api.deepseek.com", 443), timeout=1.5)
        self.assertIs(status["capabilities"]["live_llm_configured"], True)
        self.assertIs(status["capabilities"]["live_llm_network"], True)
        self.assertIs(status["capabilities"]["live_llm"], True)

    def test_live_llm_is_unavailable_without_config(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_config = Path(directory) / "missing.json"
            with patch.dict(os.environ, {"OPENAI_CONFIG_FILE": str(missing_config)}, clear=True):
                with patch("agent.environment_status.socket.create_connection") as create_connection:
                    status = environment_status()

        create_connection.assert_not_called()
        self.assertIs(status["capabilities"]["live_llm_configured"], False)
        self.assertIs(status["capabilities"]["live_llm_network"], False)
        self.assertIs(status["capabilities"]["live_llm"], False)

    def test_reports_invalid_explicit_gdal_and_proj_data_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "OPENAI_CONFIG_FILE": str(Path(directory) / "missing.json"),
                    "GDAL_DATA": str(Path(directory) / "gdal"),
                    "PROJ_LIB": str(Path(directory) / "proj"),
                },
                clear=True,
            ):
                status = environment_status()

        self.assertIs(status["data"]["gdal_data_available"], False)
        self.assertIs(status["data"]["proj_data_available"], False)


if __name__ == "__main__":
    unittest.main()
