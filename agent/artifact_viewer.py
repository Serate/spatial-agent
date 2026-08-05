import html
import json
from typing import Any, Dict


def render_artifact_html(artifact: Dict[str, Any]) -> str:
    """Render a self-contained, dependency-free HTML view of a run artifact."""
    title = html.escape(str(artifact.get("run_id", "Agent run")))
    status = html.escape(str(artifact.get("status", "UNKNOWN")))
    request = html.escape(str(artifact.get("request") or ""))
    answer = html.escape(str(artifact.get("answer") or ""))
    error = html.escape(str(artifact.get("error") or ""))
    plan = artifact.get("plan") or {}
    planner_metrics = artifact.get("planner_metrics") or {}
    goal = html.escape(str(plan.get("goal") or "No plan generated"))
    steps = artifact.get("steps") or []
    step_rows = "".join(_step_row(step) for step in steps)
    trace_rows = "".join(
        "<li>" + html.escape(str(line)) + "</li>"
        for line in artifact.get("trace_summary", [])
    )
    detail = "<p class=error>" + error + "</p>" if error else ""
    metrics_text = html.escape(json.dumps(planner_metrics, ensure_ascii=False, sort_keys=True))
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spatial Agent Run {title}</title>
<style>
:root {{ color-scheme: light; font-family: Inter,Segoe UI,Arial,sans-serif; color:#17202a; background:#f4f6f8; }}
body {{ margin:0; }}
main {{ max-width:1040px; margin:0 auto; padding:32px 20px 56px; }}
header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:24px; margin-bottom:24px; }}
h1 {{ margin:0 0 8px; font-size:28px; }} h2 {{ margin:0 0 14px; font-size:17px; }}
.muted {{ color:#5f6b76; }} .status {{ font-weight:700; color:#146c43; }}
section {{ background:#fff; border:1px solid #d9e0e6; border-radius:8px; padding:20px; margin-top:16px; }}
.prompt {{ font-size:18px; line-height:1.5; }} .answer {{ line-height:1.6; white-space:pre-wrap; }}
.error {{ color:#a61b1b; white-space:pre-wrap; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:11px 10px; border-top:1px solid #e5e9ed; vertical-align:top; }} th {{ color:#5f6b76; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
code {{ background:#eef1f4; padding:2px 5px; border-radius:4px; }} ul {{ margin:0; padding-left:20px; line-height:1.7; }}
@media (max-width:640px) {{ header {{ display:block; }} table {{ display:block; overflow-x:auto; white-space:nowrap; }} }}
</style></head><body><main>
<header><div><div class="muted">Spatial Agent run</div><h1>{title}</h1><div class="muted">{request}</div></div><div class="status">{status}</div></header>
<section><h2>Plan</h2><div class="prompt">{goal}</div></section>
<section><h2>Planner Metrics</h2><code>{metrics}</code></section>
<section><h2>Tool Steps</h2><table><thead><tr><th>Tool</th><th>Status</th><th>Attempts</th><th>Latency</th><th>Result</th></tr></thead><tbody>{step_rows}</tbody></table>{detail}</section>
<section><h2>Answer</h2><div class="answer">{answer}</div></section>
<section><h2>Trace</h2><ul>{trace_rows}</ul></section>
</main></body></html>""".format(
        title=title,
        status=status,
        request=request,
        goal=goal,
        metrics=metrics_text,
        step_rows=step_rows or '<tr><td colspan="5" class="muted">No tool steps</td></tr>',
        detail=detail,
        answer=answer,
        trace_rows=trace_rows or '<li class="muted">No trace entries</li>',
    )


def _step_row(step: Any) -> str:
    if not isinstance(step, dict):
        return "<tr><td colspan=\"5\">Invalid step summary</td></tr>"
    result = step.get("result") or {}
    result_text = html.escape(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return "<tr><td><code>{}</code></td><td>{}</td><td>{}</td><td>{} ms</td><td>{}</td></tr>".format(
        html.escape(str(step.get("tool") or "")),
        html.escape(str(step.get("status") or "")),
        html.escape(str(step.get("attempts", 0))),
        html.escape(str(step.get("latency_ms") or "-")),
        result_text,
    )
