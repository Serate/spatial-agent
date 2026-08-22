import html
import json
from typing import Any, Dict

from .evidence_projection import project_evidence_projection
from .evidence_recovery import project_evidence_recovery


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
    views_html = _views_section(artifact)
    evidence_html = _evidence_section(artifact)
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
.view-grid,.view-rows,.evidence-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin-top:12px; }}
.metric,.view-row {{ border:1px solid #e5e9ed; border-radius:8px; padding:12px; background:#f8fafc; }}
.view-row small {{ display:block; color:#5f6b76; margin-bottom:4px; }} .view-row b {{ word-break:break-word; }}
.chart-view {{ display:grid; gap:8px; margin:14px 0; }} .chart-row {{ display:grid; grid-template-columns:minmax(90px,150px) minmax(120px,1fr) auto; gap:10px; align-items:center; }}
.chart-label {{ color:#334155; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }} .chart-track {{ height:10px; border-radius:999px; background:#e5e9ed; overflow:hidden; }}
.chart-fill {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,#0f766e,#d97706); }} .chart-value {{ color:#17202a; font-size:12px; white-space:nowrap; }}
.metric b {{ display:block; font-size:18px; margin-bottom:4px; }} .panel-kind {{ color:#5f6b76; font-size:12px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:11px 10px; border-top:1px solid #e5e9ed; vertical-align:top; }} th {{ color:#5f6b76; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
code {{ background:#eef1f4; padding:2px 5px; border-radius:4px; }} ul {{ margin:0; padding-left:20px; line-height:1.7; }}
@media (max-width:640px) {{ header {{ display:block; }} table {{ display:block; overflow-x:auto; white-space:nowrap; }} }}
</style></head><body><main>
<header><div><div class="muted">Spatial Agent run</div><h1>{title}</h1><div class="muted">{request}</div></div><div class="status">{status}</div></header>
<section><h2>Plan</h2><div class="prompt">{goal}</div></section>
{evidence_html}
<section><h2>Planner Metrics</h2><code>{metrics}</code></section>
{views_html}
<section><h2>Tool Steps</h2><table><thead><tr><th>Tool</th><th>Status</th><th>Attempts</th><th>Latency</th><th>Result</th></tr></thead><tbody>{step_rows}</tbody></table>{detail}</section>
<section><h2>Answer</h2><div class="answer">{answer}</div></section>
<section><h2>Trace</h2><ul>{trace_rows}</ul></section>
</main></body></html>""".format(
        title=title,
        status=status,
        request=request,
        goal=goal,
        evidence_html=evidence_html,
        metrics=metrics_text,
        views_html=views_html,
        step_rows=step_rows or '<tr><td colspan="5" class="muted">No tool steps</td></tr>',
        detail=detail,
        answer=answer,
        trace_rows=trace_rows or '<li class="muted">No trace entries</li>',
    )


def _evidence_section(artifact: Dict[str, Any]) -> str:
    """Render the shared evidence projection without exposing raw payloads."""
    projection = project_evidence_projection(artifact)
    recovery = project_evidence_recovery(artifact)
    registry = projection.get("evidence_registry") or {}
    entries = registry.get("entries") if isinstance(registry.get("entries"), list) else []
    migration = projection.get("migration") or {}
    completeness = projection.get("evidence_registry_completeness") or {}
    selection = projection.get("selection") or {}
    workflow = selection.get("workflow_selection") or {}
    planner = selection.get("planner_selection") or {}
    entry_rows = "".join(
        "<li><strong>{}</strong> · {} · <code>{}</code> · {}</li>".format(
            html.escape(_entry_label(item.get("id"))),
            html.escape(str(item.get("state") or "unknown")),
            html.escape(str(item.get("schema_version") or "unknown")),
            html.escape(str(item.get("reference") or "")),
        )
        for item in entries[:16]
        if isinstance(item, dict)
    )
    registry_state = "可用" if registry.get("available") else "不可用"
    complete_state = "完整" if completeness.get("passed") else "不完整"
    migration_state = str(migration.get("state") or "unavailable")
    recovery_labels = {
        "ready": "可用",
        "recoverable": "可恢复",
        "blocked": "已阻断",
        "unavailable": "不可用",
    }
    recovery_state = recovery_labels.get(
        str(recovery.get("state") or "unavailable"), "未知"
    )
    recovery_actions = "、".join(
        str(item)[:64]
        for item in (recovery.get("allowed_actions") or [])
    ) or "无"
    return """<section><h2>证据索引（Evidence Registry）</h2>
<p class="muted">Registry：{registry_state} · {count} 个入口 · 完整性：{complete_state} · 迁移状态：{migration_state}</p>
<div class="evidence-grid">{workflow_card}{planner_card}</div>
<p class="muted">schema：{schema} · 迁移动作：{action} · 恢复状态：{recovery_state} · 允许动作：{recovery_actions}</p>
<ul>{entries}</ul></section>""".format(
        registry_state=html.escape(registry_state),
        count=html.escape(str(registry.get("entry_count") or 0)),
        complete_state=html.escape(complete_state),
        migration_state=html.escape(migration_state),
        schema=html.escape(str(registry.get("schema_version") or "unknown")),
        action=html.escape(str(migration.get("action") or "none")),
        recovery_state=html.escape(recovery_state),
        recovery_actions=html.escape(recovery_actions),
        workflow_card=_selection_card("工作流选择", workflow),
        planner_card=_selection_card("规划器选择", planner),
        entries=entry_rows or '<li class="muted">没有可读取的证据入口</li>',
    )


def _selection_card(title: str, selection: Dict[str, Any]) -> str:
    rows = []
    for label, key in (
        ("状态", "state"),
        ("原因", "reason_code"),
        ("能力", "selected_capability_id"),
        ("计划能力", "planner_capability_id"),
        ("结果类型", "result_type"),
        ("来源", "source"),
        ("规划器", "planner_kind"),
    ):
        value = selection.get(key)
        if value:
            rows.append("<div class=\"view-row\"><small>{}</small><b>{}</b></div>".format(
                html.escape(label), html.escape(str(value))[:320]
            ))
    return "<article><h3>{}</h3><div class=\"view-rows\">{}</div></article>".format(
        html.escape(title), "".join(rows) or '<p class="muted">不可用</p>'
    )


def _entry_label(entry_id: Any) -> str:
    labels = {
        "workflow_selection": "工作流选择",
        "planner_selection": "规划器选择",
        "plan_quality": "计划质量",
        "execution_timeline": "执行时间线",
        "action_lifecycle": "动作生命周期",
        "replanning": "计划修复",
        "result": "结果契约",
    }
    text = str(entry_id or "unknown")
    return labels.get(text, text[:96])


def _views_section(artifact: Dict[str, Any]) -> str:
    result = artifact.get("result") if isinstance(artifact.get("result"), dict) else {}
    views = result.get("views") if isinstance(result.get("views"), dict) else (artifact.get("views") if isinstance(artifact.get("views"), dict) else {})
    panels = views.get("panels") if isinstance(views.get("panels"), dict) else {}
    if not panels:
        return ""
    schema = html.escape(str(views.get("schema_version") or "unknown"))
    panel_html = "".join(
        _view_panel(panel_name, panel)
        for panel_name, panel in sorted(panels.items())
        if isinstance(panel, dict)
    )
    return '<section><h2>Result Views</h2><div class="muted">{}</div>{}</section>'.format(
        schema,
        panel_html or '<p class="muted">No view panels</p>',
    )


def _view_panel(panel_name: str, panel: Dict[str, Any]) -> str:
    title = html.escape(str(panel.get("title") or panel_name))
    name = html.escape(str(panel_name))
    kind = html.escape(str(panel.get("kind") or "unknown"))
    metrics = panel.get("metrics") if isinstance(panel.get("metrics"), list) else []
    metric_html = "".join(_metric_card(metric) for metric in metrics[:12])
    row_html = _view_rows(panel.get("rows"))
    chart_html = _view_chart(panel)
    table_html = _view_table(panel.get("table"))
    note = panel.get("note")
    note_html = '<p class="muted">{}</p>'.format(html.escape(str(note))) if note else ""
    return '<article><h3>{}</h3><div class="panel-kind"><code>{}</code> · {}</div><div class="view-grid">{}</div>{}{}{}{}</article>'.format(
        title,
        name,
        kind,
        metric_html or '<div class="muted">No metrics</div>',
        row_html,
        chart_html,
        table_html,
        note_html,
    )


def _metric_card(metric: Any) -> str:
    if not isinstance(metric, dict):
        return ""
    label = html.escape(str(metric.get("label") or "Metric"))
    value = html.escape(str(metric.get("value") if metric.get("value") is not None else "-"))
    return '<div class="metric"><b>{}</b><span>{}</span></div>'.format(value, label)


def _view_rows(rows: Any) -> str:
    if not isinstance(rows, list):
        return ""
    items = []
    for row in rows[:16]:
        if isinstance(row, dict):
            label = row.get("label") or "Field"
            value = row.get("value") if row.get("value") is not None else "-"
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            label, value = row[0], row[1]
        else:
            continue
        items.append(
            '<div class="view-row"><small>{}</small><b>{}</b></div>'.format(
                html.escape(str(label))[:160],
                html.escape(str(value))[:320],
            )
        )
    return '<div class="view-rows">{}</div>'.format("".join(items)) if items else ""


def _view_table(table: Any) -> str:
    if not isinstance(table, dict):
        return ""
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    if not rows:
        return ""
    columns = table.get("columns") if isinstance(table.get("columns"), list) else []
    normalized_rows = [_normalize_table_row(row) for row in rows[:50]]
    column_count = min(12, max(len(columns), *(len(row) for row in normalized_rows)))
    if column_count <= 0:
        return ""
    if not columns:
        columns = ["Column {}".format(index + 1) for index in range(column_count)]
    header = "".join("<th>{}</th>".format(html.escape(str(col))[:160]) for col in columns[:column_count])
    body = "".join(
        "<tr>{}</tr>".format(
            "".join(
                "<td>{}</td>".format(html.escape(str(row[index] if index < len(row) else "-"))[:320])
                for index in range(column_count)
            )
        )
        for row in normalized_rows
    )
    return '<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>'.format(header, body)


def _view_chart(panel: Dict[str, Any]) -> str:
    if not isinstance(panel, dict) or panel.get("kind") != "comparison_chart":
        return ""
    series = panel.get("series") if isinstance(panel.get("series"), list) else []
    points = []
    for item in series[:1]:
        if isinstance(item, dict) and isinstance(item.get("points"), list):
            points.extend(point for point in item["points"] if isinstance(point, dict))
    values = []
    for point in points:
        try:
            values.append(float(point.get("y")))
        except (TypeError, ValueError):
            pass
    maximum = max(values) if values else 1.0
    rows = []
    for point in points[:50]:
        try:
            value = float(point.get("y"))
        except (TypeError, ValueError):
            continue
        width = max(2.0, min(100.0, value / maximum * 100 if maximum else 0))
        rows.append(
            '<div class="chart-row"><span class="chart-label">{}</span><span class="chart-track"><i class="chart-fill" style="width:{:.2f}%"></i></span><span class="chart-value">{}</span></div>'.format(
                html.escape(str(point.get("label") or point.get("x") or "-"))[:160],
                width,
                html.escape(_compact_chart_value(value)),
            )
        )
    return '<div class="chart-view">{}</div>'.format("".join(rows)) if rows else ""


def _compact_chart_value(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return "{:.4g}".format(value)


def _normalize_table_row(row: Any) -> list[Any]:
    if isinstance(row, dict):
        return list(row.values())[:12]
    if isinstance(row, (list, tuple)):
        return list(row)[:12]
    return [row]


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
