"""Minimal static contract for domain-aware Console controls.

This test deliberately does not boot HTTP, a browser, or a GIS backend.  The
Console must obtain the selected domain from ``/capabilities`` and gate the
fixed GIS controls before any result renderer is involved.
"""

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


class _DomainControlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        marker = attributes.get("data-domain-control")
        if marker:
            self.controls.append(
                {
                    "tag": tag,
                    "id": attributes.get("id", ""),
                    "class": attributes.get("class", ""),
                    "value": attributes.get("value", ""),
                    "domains": {
                        value.strip().lower()
                        for value in re.split(r"[\s,]+", marker)
                        if value.strip()
                    },
                }
            )


class M148ConsoleDomainStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            Path(__file__).resolve().parents[1] / "web" / "index.html"
        ).read_text(encoding="utf-8")
        parser = _DomainControlParser()
        parser.feed(cls.source)
        cls.controls = parser.controls

    def test_text_domain_gates_every_fixed_gis_control(self):
        self.assertGreaterEqual(len(self.controls), 4)
        self.assertTrue(
            any(
                item["tag"] == "option" and item["value"] == "local"
                for item in self.controls
            )
        )
        expected_classes = {
            "suggestions",
            "hint",
            "compare-result",
            "map-result",
        }
        marked_classes = {
            class_name
            for item in self.controls
            for class_name in item["class"].split()
        }
        self.assertTrue(expected_classes.issubset(marked_classes))
        for item in self.controls:
            self.assertEqual(
                item["domains"],
                {"gis"},
                msg=f"fixed control is not GIS-gated: {item}",
            )

        # A Text domain is never an allowlisted domain for a GIS marker.
        self.assertTrue(all("text" not in item["domains"] for item in self.controls))

        # The runtime gate must hide the marker and disable all descendants,
        # so a hidden comparison/map button cannot remain operable.
        self.assertRegex(self.source, r"control\.hidden\s*=\s*!allowed")
        self.assertRegex(self.source, r"control\.setAttribute\('aria-hidden'")
        self.assertRegex(self.source, r"element\.disabled\s*=\s*true")
        self.assertRegex(
            self.source,
            r"querySelectorAll\('button, input, select, textarea, option, \[tabindex\]'\)",
        )

    def test_domain_id_is_read_from_capabilities_without_gis_renderer_branch(self):
        self.assertIn("nativeFetch('/capabilities'+query)", self.source)
        self.assertRegex(self.source, r"setDomainControlState\(data\.domain_id\)")
        self.assertIn("setDomainControlState('unknown')", self.source)

        renderer_start = self.source.index("function genericResult(data)")
        renderer_end = self.source.index(
            "function resultViewPanels(data)", renderer_start
        )
        generic_renderer = self.source[renderer_start:renderer_end]
        for gis_specific_id in (
            "rasterStats",
            "healthStats",
            "overviewStats",
            "compositeStats",
            "buildabilityStats",
            "compareResults",
            "mapSelection",
        ):
            self.assertNotIn(gis_specific_id, generic_renderer)


if __name__ == "__main__":
    unittest.main()
