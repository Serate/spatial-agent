import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.errors import ToolError
from agent.service import AgentService
from agent.tools import ToolRegistry
from serve_api import AgentApiHandler


def static_registry():
    definitions = {
        "make_value": {
            "name": "make_value",
            "input_schema": {"type": "object", "additionalProperties": True},
        }
    }

    class StaticAdapter:
        def invoke(self, name, arguments):
            if name == "make_value":
                return {"value": 1}
            raise ToolError("Adapter does not implement: " + name)

    return ToolRegistry(definitions, StaticAdapter())


class M81DynamicToolRegistryTests(unittest.TestCase):
    def test_register_tool_accepts_valid_input(self):
        registry = static_registry()
        result = registry.register_tool(
            "estimate_area",
            {
                "description": "估算面积",
                "input_schema": {
                    "type": "object",
                    "properties": {"coordinates": {"type": "array"}},
                },
            },
            lambda args: {"area": 1.0},
        )
        self.assertTrue(result["dynamic"])
        self.assertEqual(result["name"], "estimate_area")
        self.assertIn("estimate_area", registry.names)

    def test_register_tool_rejects_invalid_names(self):
        registry = static_registry()
        for bad in ("", "HasUpper", "1bad", "bad-name"):
            with self.assertRaises(ToolError):
                registry.register_tool(bad, {"input_schema": {"type": "object"}}, lambda args: {})

    def test_register_tool_rejects_duplicate(self):
        registry = static_registry()
        registry.register_tool("dup", {"input_schema": {"type": "object"}}, lambda args: {})
        with self.assertRaises(ToolError):
            registry.register_tool("dup", {"input_schema": {"type": "object"}}, lambda args: {})
        with self.assertRaises(ToolError):
            registry.register_tool("make_value", {"input_schema": {"type": "object"}}, lambda args: {})

    def test_register_tool_rejects_bad_definition_or_handler(self):
        registry = static_registry()
        with self.assertRaises(ToolError):
            registry.register_tool("x", {}, lambda args: {})
        with self.assertRaises(ToolError):
            registry.register_tool("x", {"input_schema": {"type": "string"}}, lambda args: {})
        with self.assertRaises(ToolError):
            registry.register_tool("x", {"input_schema": {"type": "object"}}, "not-callable")

    def test_invoke_uses_dynamic_handler_and_validates_schema(self):
        registry = static_registry()
        registry.register_tool(
            "double",
            {
                "input_schema": {
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "number"}},
                }
            },
            lambda args: {"doubled": args["value"] * 2},
        )
        self.assertEqual(registry.invoke("double", {"value": 21}), {"doubled": 42})
        with self.assertRaises(ToolError):
            registry.invoke("double", {})  # missing required
        with self.assertRaises(ToolError):
            registry.invoke("double", {"value": "x"})  # wrong type

    def test_static_tools_unaffected_by_registration(self):
        registry = static_registry()
        registry.register_tool("extra", {"input_schema": {"type": "object"}}, lambda args: {})
        self.assertEqual(registry.invoke("make_value", {}), {"value": 1})

    def test_dynamic_tools_lists_bounded_summaries(self):
        registry = static_registry()
        registry.register_tool(
            "alpha", {"description": "第一个", "input_schema": {"type": "object"}}, lambda args: {}
        )
        registry.register_tool(
            "beta", {"description": "第二个", "input_schema": {"type": "object"}}, lambda args: {}
        )
        tools = registry.dynamic_tools()
        self.assertEqual([item["name"] for item in tools], ["alpha", "beta"])


class M81DynamicToolServiceTests(unittest.TestCase):
    def test_service_register_and_invoke_estimate_area(self):
        service = AgentService()
        try:
            registered = service.register_tool(
                "estimate_area",
                {
                    "description": "估算区域面积（演示）",
                    "input_schema": {
                        "type": "object",
                        "required": ["coordinates"],
                        "properties": {"coordinates": {"type": "array"}},
                    },
                },
                AgentService.estimate_area_handler,
            )
            self.assertTrue(registered["dynamic"])
            listed = service.list_dynamic_tools()
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["dynamic_tools"][0]["name"], "estimate_area")
            # Run a request that uses the dynamic tool via a manual invocation.
            runtime = service._runtime("rule", "memory")
            result = runtime._registry.invoke(
                "estimate_area", {"coordinates": [[0, 0], [1, 0], [1, 1], [0, 1]]}
            )
            self.assertEqual(result["vertices"], 4)
            self.assertAlmostEqual(result["estimated_area_degrees"], 1.0)
        finally:
            service.close()

    def test_estimate_area_rejects_bad_input(self):
        with self.assertRaises(ToolError):
            AgentService.estimate_area_handler({"coordinates": [[0, 0], [1, 0]]})
        with self.assertRaises(ToolError):
            AgentService.estimate_area_handler({})


class M81DynamicToolHttpTests(unittest.TestCase):
    def test_http_register_and_list(self):
        class TestHandler(AgentApiHandler):
            service = AgentService(state_db_path=None)

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request(
                    "POST",
                    "/tools",
                    body=json.dumps({
                        "name": "estimate_area",
                        "definition": {
                            "description": "估算区域面积（演示）",
                            "input_schema": {"type": "object", "properties": {"coordinates": {"type": "array"}}},
                        },
                    }),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertTrue(payload["dynamic"])

                connection.request("GET", "/tools/dynamic")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                listed = json.loads(response.read().decode("utf-8"))
                self.assertGreaterEqual(listed["count"], 1)
                names = [item["name"] for item in listed["dynamic_tools"]]
                self.assertIn("estimate_area", names)
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TestHandler.service.close()


if __name__ == "__main__":
    unittest.main()
