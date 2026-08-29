"""Opt-in live acceptance for proposal approval and same-run recovery.

The report is deliberately limited to statuses, counts, identities and
reason codes. It never prints proposal source, model output, prompts or keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping


LIVE_ENV = "SPATIAL_AGENT_LIVE_HTTP"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "REJECTED"}
WAITING = "WAITING_FOR_DECISION"


class AcceptanceFailure(RuntimeError):
    pass


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if not args.allow_live and os.environ.get(LIVE_ENV, "").lower() not in {"1", "true", "yes"}:
        print(json.dumps({"status": "skipped", "reason_code": "live_http_opt_in_required"}))
        return 2
    try:
        report = run_acceptance(args)
    except AcceptanceFailure as exc:
        print(json.dumps({"status": "failed", "reason_code": "tool_proposal_acceptance_failed", "error_type": type(exc).__name__, "message": str(exc)[:240]}))
        return 1
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


def run_acceptance(args) -> dict:
    base = str(args.base_url).rstrip("/")
    proposal_name = "live_sum_average_" + uuid.uuid4().hex[:8]
    request = (
        "请完成一个纯计算任务：计算数字数组 [10, 20, 30, 40] 的总和与平均值。"
        "现有目录没有直接提供这个纯数学工具，请让模型提出一个名为 " + proposal_name + " 的新沙箱Python工具："
        "输入参数只包含数字数组 values，输出该数组的 sum 和 average。"
        "这是纯计算，不需要读取洪山区文件，也不需要联网；源码只能使用 arguments['values']、sum、len、float、dict 等"
        "允许的内置函数，不得出现 open、import、属性访问、文件、网络或系统操作。提出后等待人工审批，"
        "审批前不要执行该工具；审批通过后必须调用这个新工具一次，传入 values=[10,20,30,40]，"
        "再用通俗中文给出简短结论。"
    )
    payload = {
        "request": request,
        "planner": "openai",
        "backend": "local",
        "session_id": "live-m328-proposal-" + uuid.uuid4().hex,
        "export_artifact": True,
        "idempotency_key": "live-m328-proposal-" + uuid.uuid4().hex,
    }
    initial = _json_request(base, "POST", "/domains/economic/runs", payload, args.http_timeout)
    initial_status = _status(initial)
    run_id = _text(initial.get("run_id"))
    receipt = initial.get("action_receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    approval = receipt.get("approval")
    approval = approval if isinstance(approval, Mapping) else {}
    if initial_status != WAITING:
        failure = initial.get("failure") if isinstance(initial.get("failure"), Mapping) else {}
        planning_failure = initial.get("planning_failure") if isinstance(initial.get("planning_failure"), Mapping) else {}
        code = _text(initial.get("error_code") or failure.get("code") or planning_failure.get("code") or "unknown")
        phase = _text(failure.get("phase") or planning_failure.get("phase") or "unknown")
        raise AcceptanceFailure("proposal request did not enter approval wait: " + initial_status + ", phase=" + phase + ", code=" + code)
    if not run_id or _text(approval.get("run_id")) != run_id:
        raise AcceptanceFailure("approval receipt is not bound to the waiting run")
    approval_id = _text(approval.get("approval_id"))
    fingerprint = _text(approval.get("receipt_fingerprint"))
    version = approval.get("version")
    if not approval_id or not fingerprint or not isinstance(version, int):
        raise AcceptanceFailure("approval receipt identity is incomplete")

    resolved = _json_request(
        base,
        "POST",
        "/domains/economic/tools/approvals/" + approval_id + "/resolve",
        {
            "action": args.approval_action,
            "expected_version": version,
            "receipt_fingerprint": fingerprint,
            "actor_id": "live-acceptance",
        },
        args.http_timeout,
    )
    resolved_run = resolved.get("run")
    resolved_run = resolved_run if isinstance(resolved_run, Mapping) else resolved
    resolved_status = _status(resolved_run)
    if args.approval_action == "approve":
        if _text(resolved_run.get("run_id")) != run_id:
            raise AcceptanceFailure("approved run identity changed")
        resolved_run = _wait_for_terminal(base, run_id, args)
        resolved_status = _status(resolved_run)
        if resolved_status != "COMPLETED":
            failure = resolved_run.get("failure") if isinstance(resolved_run.get("failure"), Mapping) else {}
            code = _text(resolved_run.get("error_code") or failure.get("code") or "unknown")
            phase = _text(failure.get("phase") or "unknown")
            raise AcceptanceFailure("approved run ended with " + resolved_status + ", phase=" + phase + ", code=" + code)
    elif resolved_status not in {"REJECTED", "CANCELLED"}:
        raise AcceptanceFailure("rejected proposal did not close the run")

    steps = resolved_run.get("steps")
    steps = steps if isinstance(steps, list) else []
    tool_names = [_text(item.get("tool")) for item in steps if isinstance(item, Mapping) and _text(item.get("tool"))]
    if args.approval_action == "approve" and proposal_name not in tool_names:
        raise AcceptanceFailure(
            "approved proposal was not executed; observed_tools="
            + ",".join(tool_names[:12])
        )
    answer_evidence = resolved_run.get("answer_generation_evidence")
    answer_evidence = answer_evidence if isinstance(answer_evidence, Mapping) else {}
    return {
        "status": "ok",
        "initial_status": initial_status,
        "initial_step_count": len(initial.get("steps") or []) if isinstance(initial.get("steps"), list) else 0,
        "approval": {
            "action": args.approval_action,
            "status": _text(resolved.get("approval", {}).get("status")) if isinstance(resolved.get("approval"), Mapping) else args.approval_action + "d",
            "run_identity_preserved": _text(resolved_run.get("run_id")) == run_id,
            "receipt_state": _text((resolved_run.get("action_receipt") or {}).get("state")) if isinstance(resolved_run.get("action_receipt"), Mapping) else "",
        },
        "resolved_status": resolved_status,
        "resolved_step_count": len(steps),
        "tool_names": tool_names[:12],
        "proposal_executed": proposal_name in tool_names,
        "answer_streaming": answer_evidence.get("streaming") is True,
        "result_type": _text(resolved_run.get("result_type")),
    }


def _wait_for_terminal(base: str, run_id: str, args) -> dict:
    for _ in range(args.poll_limit):
        current = _json_request(
            base,
            "GET",
            "/domains/economic/runs/" + run_id,
            None,
            args.http_timeout,
        )
        if _status(current) in TERMINAL:
            return current
        time.sleep(max(0.05, min(args.poll_interval, 5.0)))
    raise AcceptanceFailure("approved run did not reach a terminal state")


def _json_request(base: str, method: str, path: str, payload, timeout: float) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        safe_code = "http_error"
        try:
            error_body = json.loads(exc.read(32 * 1024).decode("utf-8"))
            if isinstance(error_body, Mapping):
                safe_code = _text(error_body.get("error_code") or error_body.get("code") or safe_code)
        except Exception:
            pass
        raise AcceptanceFailure("HTTP request failed: status=" + str(exc.code) + ", code=" + safe_code) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise AcceptanceFailure("HTTP request failed: " + type(exc).__name__) from exc
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceFailure("HTTP response was not JSON") from exc
    if not isinstance(value, dict):
        raise AcceptanceFailure("HTTP response was not an object")
    return value


def _status(value: Mapping) -> str:
    return _text(value.get("status")).upper() or "UNKNOWN"


def _text(value) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ")[:160]


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--http-timeout", type=float, default=30.0)
    parser.add_argument("--poll-limit", type=int, default=120)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--approval-action", choices=("approve", "reject"), default="approve")
    parser.add_argument("--allow-live", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
