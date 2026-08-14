"""Answer quality judging (M80.4).

Default is a deterministic heuristic judge (offline, CI-safe, no tokens):
it scores four dimensions (completeness, groundedness, clarity,
explanatory) on 0-5 scales by checking the answer against the request and
the bounded evidence steps. An optional LLM-as-judge path reuses the normal
OpenAI-compatible client to score the same dimensions; its output is
redacted (scores + one-line reason only, never the raw answer or provider
payload).

The judge is additive: it never changes the existing structured contract
passed/failed semantics.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

_CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_GARBLED_RE = re.compile(r"[\ufffd]|(?:\\u[0-9a-fA-F]{4}){2,}")

_JUDGE_LLM_ENV = "SPATIAL_AGENT_JUDGE_LLM"

_DISCLAIMER_TERMS = (
    "演示",
    "不代表",
    "非规划许可",
    "仅供演示",
    "仅用于演示",
    "不构成",
    "限制",
    "样本",
)

_JUDGE_SCHEMA = {
    "type": "object",
    "required": ["scores", "passed"],
    "additionalProperties": False,
    "properties": {
        "scores": {
            "type": "object",
            "required": ["completeness", "groundedness", "clarity", "explanatory"],
            "properties": {
                "completeness": {"type": "number"},
                "groundedness": {"type": "number"},
                "clarity": {"type": "number"},
                "explanatory": {"type": "number"},
            },
        },
        "passed": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}


def judge_llm_enabled() -> bool:
    raw = os.environ.get(_JUDGE_LLM_ENV)
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def heuristic_answer_judge(
    answer: Optional[str],
    steps: Iterable[Mapping[str, Any]],
    request: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic, offline answer quality judging."""
    answer_text = str(answer or "")
    evidence = _evidence_numbers(steps)
    scores = {
        "completeness": _score_completeness(answer_text, request),
        "groundedness": _score_groundedness(answer_text, evidence),
        "clarity": _score_clarity(answer_text),
        "explanatory": _score_explanatory(answer_text),
    }
    passed = all(score >= 3 for score in scores.values())
    return {
        "mode": "heuristic",
        "scores": scores,
        "passed": passed,
        "reason": _heuristic_reason(scores, answer_text),
        "evidence_number_count": len(evidence),
    }


def llm_answer_judge(
    answer: Optional[str],
    steps: Iterable[Mapping[str, Any]],
    request: Optional[str] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Optional LLM-as-judge scoring using an OpenAI-compatible client.

    The prompt only carries the answer and a bounded evidence summary; the
    result is redacted to scores + one-line reason. Falls back to the
    heuristic judge when the model call fails.
    """
    answer_text = str(answer or "")
    evidence = _evidence_summary(steps)
    if client is None or not answer_text:
        return heuristic_answer_judge(answer, steps, request)
    prompt = (
        "你是答案质量评审员。请按 0-5 分为以下四个维度打分：\n"
        "completeness（是否覆盖请求核心要素）、groundedness（结论是否与证据一致）、"
        "clarity（中文可读性、无乱码）、explanatory（是否说明数据/方法/限制）。\n"
        "请求：" + str(request or "") + "\n"
        "答案：" + answer_text[:1500] + "\n"
        "证据摘要：" + (evidence or "无") + "\n"
        "返回 JSON：scores(四维 0-5)、passed(全部>=3)、reason(一句话，中文)。"
    )
    try:
        payload = client.complete_json(
            [{"role": "user", "content": prompt}], _JUDGE_SCHEMA
        )
        scores = payload.get("scores") or {}
        return {
            "mode": "llm",
            "scores": {
                "completeness": _bound_score(scores.get("completeness")),
                "groundedness": _bound_score(scores.get("groundedness")),
                "clarity": _bound_score(scores.get("clarity")),
                "explanatory": _bound_score(scores.get("explanatory")),
            },
            "passed": bool(payload.get("passed", False)),
            "reason": str(payload.get("reason") or "")[:200],
            "evidence_number_count": len(_evidence_numbers(steps)),
        }
    except Exception:
        return heuristic_answer_judge(answer, steps, request)


def answer_judge_report(
    answer: Optional[str],
    steps: Iterable[Mapping[str, Any]],
    request: Optional[str] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Public entry: heuristic by default, LLM when enabled and client given."""
    if judge_llm_enabled() and client is not None:
        return llm_answer_judge(answer, steps, request, client=client)
    return heuristic_answer_judge(answer, steps, request)


# --------------------------------------------------------------------------- #
# Heuristic scoring internals
# --------------------------------------------------------------------------- #


def _score_completeness(answer: str, request: Optional[str]) -> int:
    if not answer:
        return 0
    score = 3
    if request:
        # A credible answer usually echoes at least one salient token of the
        # request (region name, dataset, metric word).
        terms = [term for term in _salient_request_terms(request)]
        matched = sum(1 for term in terms if term in answer)
        if terms and matched >= 1:
            score += 1
        if terms and matched >= max(2, len(terms) // 2):
            score += 1
    if len(answer) >= 40:
        score += 1
    return min(5, score)


def _score_groundedness(answer: str, evidence_numbers: List[str]) -> int:
    if not answer:
        return 0
    if not evidence_numbers:
        return 4  # No numbers in evidence; cannot contradict.
    answer_numbers = _NUMBER_RE.findall(answer)
    if not answer_numbers:
        return 2  # Answer mentions no numbers while evidence has them.
    # Every evidence number that is large/salient should appear or the answer
    # should not contradict it. Penalize when the answer's numbers are wildly
    # inconsistent with evidence magnitudes.
    evidence_ints = sorted({_to_int(value) for value in evidence_numbers if _to_int(value) is not None})
    answer_ints = sorted({_to_int(value) for value in answer_numbers if _to_int(value) is not None})
    if not evidence_ints:
        return 4
    if not answer_ints:
        return 2
    ratio = max(answer_ints) / max(evidence_ints) if evidence_ints else 1.0
    if 0.1 <= ratio <= 10:
        return 5
    if 0.01 <= ratio <= 100:
        return 3
    return 1


def _score_clarity(answer: str) -> int:
    if not answer:
        return 0
    if _GARBLED_RE.search(answer):
        return 1
    chinese_count = len(_CHINESE_RE.findall(answer))
    if chinese_count == 0:
        return 2
    if len(answer) < 20:
        return 3
    if chinese_count >= 10 and len(answer) >= 40:
        return 5
    return 4


def _score_explanatory(answer: str) -> int:
    if not answer:
        return 0
    lowered = answer.lower()
    score = 2
    if any(term in answer for term in _DISCLAIMER_TERMS):
        score += 2
    if any(token in lowered for token in ("数据", "栅格", "dem", "工具", "步骤", "样本")):
        score += 1
    return min(5, score)


def _heuristic_reason(scores: Mapping[str, int], answer: str) -> str:
    failed = [name for name, score in scores.items() if score < 3]
    if not failed:
        return "答案在四个维度均达到基本质量要求。"
    return "以下维度评分低于 3：" + "、".join(failed) + "。"


def _evidence_numbers(steps: Iterable[Mapping[str, Any]]) -> List[str]:
    numbers: List[str] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        result = step.get("result")
        if not isinstance(result, Mapping):
            continue
        statistics = result.get("statistics")
        if isinstance(statistics, Mapping):
            for key in ("candidate_pixel_count", "valid_pixel_count", "mean", "candidate_ratio"):
                value = statistics.get(key)
                if value is not None:
                    numbers.append(str(value))
        constraint = result.get("constraint_summary")
        if isinstance(constraint, Mapping):
            for key in ("eligible_features", "water_excluded_features", "candidate_features"):
                value = constraint.get(key)
                if value is not None:
                    numbers.append(str(value))
    return numbers[:20]


def _evidence_summary(steps: Iterable[Mapping[str, Any]]) -> str:
    parts = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        result = step.get("result")
        if not isinstance(result, Mapping):
            continue
        statistics = result.get("statistics")
        if isinstance(statistics, Mapping) and not statistics.get("error"):
            pieces = [
                "{}={}".format(key, statistics[key])
                for key in ("candidate_pixel_count", "valid_pixel_count", "mean", "candidate_ratio")
                if key in statistics
            ]
            if pieces:
                parts.append(step.get("tool") + ":" + ",".join(pieces))
    return "; ".join(parts)[:800]


def _salient_request_terms(request: str) -> List[str]:
    terms = []
    match = re.search(r"([\u4e00-\u9fff]{2,6}区)", request or "")
    if match:
        terms.append(match.group(1))
    for token in ("DEM", "坡度", "土地利用", "高程", "建设", "候选", "道路", "水体"):
        if token in (request or ""):
            terms.append(token)
    return terms[:6]


def _to_int(value: str) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bound_score(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, number))
