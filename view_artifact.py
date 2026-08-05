import argparse
import json
from pathlib import Path

from agent.artifact_viewer import render_artifact_html


def parse_args():
    parser = argparse.ArgumentParser(description="Render a Spatial Agent artifact as HTML.")
    parser.add_argument("artifact", help="Path to a JSON run artifact")
    parser.add_argument("--output", help="Output HTML path; defaults to artifact path with .html")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    source = Path(args.artifact)
    output = Path(args.output) if args.output else source.with_suffix(".html")
    artifact = json.loads(source.read_text(encoding="utf-8"))
    output.write_text(render_artifact_html(artifact), encoding="utf-8")
    print(output)
