"""Non-GIS Domain Pack used as an architectural integration fixture."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import domain_action_catalog, discovery_context
from agent.request_model import RequestFacts
from agent.capability_catalog import capability_catalog
from agent.result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec
from agent.workflow_templates import (
    WorkflowTemplateError,
    normalize_workflow_composition,
    normalize_workflow_selection,
    validate_workflow_plan,
    workflow_request_hint,
    workflow_template_context_summary,
)

from .catalog import (
    TEXT_CAPABILITIES,
    TEXT_DATASET_GROUPS,
    TEXT_DATASET_TOOL_CAPABILITIES,
    TEXT_TOOL_DEFINITIONS,
)
from .workflow_templates import (
    KNOWN_RESULT_TYPES,
    KNOWN_TOOL_NAMES,
    build_text_workflow_components,
    workflow_template_catalog,
)


class TextDomainPack:
    domain_id = "text"

    def action_specs(self):
        from .actions import TEXT_ACTION_SPECS

        return TEXT_ACTION_SPECS

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None):
        from .actions import execute_action

        return execute_action(action_id, payload, service=context)

    def answer_composer(self) -> Any:
        from .composer import TextAnswerComposer

        return TextAnswerComposer()

    def default_permissions(self) -> set[str]:
        return {"text_data:read"}

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> Any:
        """Return the text provider through the shared Runtime Factory seam."""
        from .provider import TextToolProvider

        return TextToolProvider()

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        return {
            "id": "text-native",
            "tool_count": len(TEXT_TOOL_DEFINITIONS),
        }

    def evidence_provider(self) -> Any:
        from .evidence import TEXT_EVIDENCE_PROVIDER

        return TEXT_EVIDENCE_PROVIDER

    def result_registry(self) -> ResultContractRegistry:
        from .views import build_views

        return ResultContractRegistry(
            {
                "text_normalize_result": ResultTypeSpec(
                    title="文本规范化",
                    panels=("generic",),
                    view_specs=(ViewSpec("generic", "generic", "规范化结果"),),
                ),
                "text_summary_result": ResultTypeSpec(
                    title="文本摘要",
                    panels=("generic",),
                    view_specs=(ViewSpec("generic", "generic", "摘要概览"),),
                ),
                "text_stats_result": ResultTypeSpec(
                    title="文本统计",
                    panels=("generic",),
                    view_specs=(ViewSpec("generic", "generic", "统计概览"),),
                ),
                "text_analysis_result": ResultTypeSpec(
                    title="组合文本分析",
                    panels=("generic",),
                    view_specs=(ViewSpec("generic", "generic", "组合结果"),),
                ),
            },
            fallback_title="运行结果",
            view_builder=build_views,
        )

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        return self.evidence_provider().runtime_snapshot(max_files=max_files)

    def release_evidence(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Text has no configured GIS volume or release manifest."""
        return self.evidence_provider().release_snapshot(
            config_path=config_path,
            max_files=max_files,
        )

    def extract_request_facts(self, request: str) -> RequestFacts:
        text = str(request or "").strip()
        lowered = text.lower()
        task_terms = {
            "normalize": ("规范化", "清洗文本", "整理文本", "normalize"),
            "stats": ("统计", "字数", "字符数", "词数", "行数", "statistics"),
            "summarize": ("摘要", "总结", "概括", "summarize", "summary"),
        }
        hits = []
        for order, (task, terms) in enumerate(task_terms.items()):
            positions = [lowered.find(term.lower()) for term in terms]
            positions = [position for position in positions if position >= 0]
            if positions:
                hits.append((min(positions), order, task))
        hits.sort()
        tasks = tuple(item[2] for item in hits) or ("summarize",)
        return RequestFacts(
            text=text,
            admin_name=None,
            tasks=tasks,
            datasets=("documents",),
            constraints={},
            evidence=("answer",),
        )

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        return capability_catalog(
            environment=environment,
            domain_id=self.domain_id,
            capability_definitions=TEXT_CAPABILITIES,
            dataset_tool_capabilities=TEXT_DATASET_TOOL_CAPABILITIES,
            dataset_groups=TEXT_DATASET_GROUPS,
            analysis_ready_capability_ids=(),
            workflow_templates=self.workflow_template_catalog(),
            actions=domain_action_catalog(self),
        )

    def discover(self, request: str, request_facts: Any) -> Mapping[str, Any]:
        from agent.capability_discovery import discover_from_catalog

        catalog = self.capability_catalog(environment="memory")
        return discover_from_catalog(
            request,
            request_facts,
            catalog.get("capabilities", ()),
        )

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Expose text selection metadata without importing spatial policy."""
        context = discovery_context(discovery, domain_id=self.domain_id)
        selection = {
            "source": "explicit_workflow" if workflow and workflow.get("template_id") else "domain_discovery",
            "selected_by": "user" if workflow and workflow.get("template_id") else "domain",
            "selected_capability_id": context.get("selected_capability_id"),
            "candidate_ids": list(context.get("candidate_ids") or [])[:8],
            "candidate_count": context.get("candidate_count"),
        }
        if isinstance(workflow, Mapping) and workflow.get("template_id"):
            normalized = self.normalize_workflow(workflow)
            selection.update(
                {
                    "source": "explicit_workflow",
                    "selected_by": "user",
                    "workflow_template_id": normalized.get("template_id"),
                    "workflow_template_version": normalized.get("template_version"),
                    "workflow_components": list(normalized.get("components") or [])[:8],
                }
            )
            if not normalized.get("components"):
                selection["workflow_components"] = []
        else:
            tasks = getattr(request_facts, "tasks", ())
            text = getattr(request_facts, "text", "")
            if isinstance(request_facts, Mapping):
                tasks = request_facts.get("tasks")
                text = request_facts.get("text", "")
            tasks = tuple(
                str(item).strip()
                for item in (tasks or ())
                if str(item).strip()
            )[:8]
            components = build_text_workflow_components(
                tasks,
                text,
            )
            if len(components) >= 2:
                selection.update(
                    {
                        "source": "domain_composition",
                        "selected_by": "domain",
                        "selected_capability_id": "text_analysis",
                        "candidate_ids": ["text_analysis"],
                        "candidate_count": 1,
                        "workflow_template_id": "text_analysis",
                        "workflow_template_version": "1.0.0",
                        "workflow_components": components,
                    }
                )
            elif selection.get("selected_capability_id") == "text_analysis":
                template = self.workflow_template_catalog().get("text_summary", {})
                selection.update(
                    {
                        "source": "domain_policy",
                        "selected_by": "domain",
                        "selected_capability_id": "text_summary",
                        "candidate_ids": ["text_summary"],
                        "candidate_count": 1,
                        "workflow_template_id": "text_summary",
                        "workflow_template_version": str(
                            template.get("version") or "1.0.0"
                        ),
                        "workflow_components": [],
                    }
                )
        return selection

    def evidence_action_guidance(
        self,
        selection: Mapping[str, Any],
        *,
        request_facts: Any = None,
    ) -> Mapping[str, Any]:
        """Recommend safe next steps from the text capability projection."""
        del request_facts
        from agent.workflow_selection import EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION

        value = selection if isinstance(selection, Mapping) else {}
        missing = value.get("missing_fields")
        selected = str(value.get("selected_capability_id") or "").strip()
        state = str(value.get("state") or "unknown").strip()
        if isinstance(missing, list) and missing:
            reason = "selection_requires_facts"
            actions = ["provide_facts"]
            guidance_state = "degraded"
        elif selected:
            reason = "text_capability_ready_for_preview"
            actions = ["preview"]
            guidance_state = "ready"
        elif state == "ambiguous":
            reason = "selection_requires_user_choice"
            actions = ["select_capability", "select_workflow"]
            guidance_state = "unknown"
        else:
            reason = "text_capability_selection_unavailable"
            actions = ["select_capability"]
            guidance_state = "unknown"
        return {
            "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
            "state": guidance_state,
            "reason_code": reason,
            "recommended_actions": actions,
            "source": "domain",
        }

    def normalize_workflow(self, workflow: Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize a Text-owned single or composed workflow."""
        if not isinstance(workflow, Mapping):
            raise ValueError("workflow must be an object")
        catalog = self.workflow_template_catalog()
        if isinstance(workflow.get("components"), (list, tuple)):
            shared_constraints = workflow.get("constraints", {})
            shared_constraints = (
                dict(shared_constraints)
                if isinstance(shared_constraints, Mapping)
                else {}
            )
            components = []
            for raw_component in workflow.get("components") or []:
                component = (
                    dict(raw_component)
                    if isinstance(raw_component, Mapping)
                    else raw_component
                )
                if isinstance(component, Mapping):
                    constraints = component.get("constraints", {})
                    constraints = (
                        dict(constraints)
                        if isinstance(constraints, Mapping)
                        else {}
                    )
                    for key, value in shared_constraints.items():
                        constraints.setdefault(key, value)
                    component["constraints"] = constraints
                components.append(component)

            def normalize_component(component: Mapping[str, Any]) -> Mapping[str, Any]:
                template_id = str(component.get("template_id") or "").strip()
                if not template_id:
                    raise ValueError("workflow component.template_id is required")
                return normalize_workflow_selection(
                    template_id,
                    component.get("constraints", {})
                    if isinstance(component.get("constraints"), Mapping)
                    else {},
                    component.get("evidence"),
                    catalog=catalog,
                    known_tools=KNOWN_TOOL_NAMES,
                    known_result_types=KNOWN_RESULT_TYPES,
                )

            return normalize_workflow_composition(
                {**dict(workflow), "components": components},
                component_normalizer=normalize_component,
                composition_template_id="text_analysis",
            )
        template_id = str(workflow.get("template_id") or "").strip()
        if not template_id:
            raise ValueError("workflow.template_id must be a non-empty string")
        constraints = workflow.get("constraints", {})
        if not isinstance(constraints, Mapping):
            raise ValueError("workflow.constraints must be an object")
        evidence = workflow.get("evidence")
        if evidence is None:
            evidence = []
        if not isinstance(evidence, (list, tuple)):
            raise ValueError("workflow.evidence must be an array")
        return normalize_workflow_selection(
            template_id,
            dict(constraints),
            evidence,
            catalog=catalog,
            known_tools=KNOWN_TOOL_NAMES,
            known_result_types=KNOWN_RESULT_TYPES,
        )

    def validate_workflow_plan(self, plan: Any, workflow: Mapping[str, Any]) -> None:
        """Validate Text-owned templates and composed plans."""
        if not isinstance(workflow, Mapping):
            raise WorkflowTemplateError("text workflow selection is incomplete")
        catalog = self.workflow_template_catalog()
        if isinstance(workflow.get("components"), (list, tuple)):
            normalize_workflow_composition(
                workflow,
                component_normalizer=lambda component: normalize_workflow_selection(
                    str(component.get("template_id") or ""),
                    component.get("constraints", {})
                    if isinstance(component.get("constraints"), Mapping)
                    else {},
                    component.get("evidence"),
                    catalog=catalog,
                    known_tools=KNOWN_TOOL_NAMES,
                    known_result_types=KNOWN_RESULT_TYPES,
                ),
                composition_template_id="text_analysis",
            )
            if not getattr(plan, "steps", None):
                raise WorkflowTemplateError("text workflow composition produced no steps")
            self.validate_plan(plan)
            return
        template_id = str(workflow.get("template_id") or "").strip()
        if not template_id:
            raise WorkflowTemplateError("text workflow selection is incomplete")
        payload = {
            "template_id": template_id,
            "template_version": workflow.get("template_version"),
            "goal": getattr(plan, "goal", ""),
            "constraints": workflow.get("constraints", {}),
            "evidence": workflow.get("evidence") or [],
            "steps": [
                {
                    "id": step.id,
                    "tool": step.tool,
                    "args": step.args,
                    "depends_on": list(step.depends_on),
                }
                for step in getattr(plan, "steps", ())
            ],
            "output": dict(getattr(plan, "output", {}) or {}),
            "assumptions": list(getattr(plan, "assumptions", ()) or ()),
        }
        validate_workflow_plan(
            template_id,
            payload,
            catalog=catalog,
            known_tools=KNOWN_TOOL_NAMES,
            known_result_types=KNOWN_RESULT_TYPES,
        )

    def validate_plan(self, plan: Any) -> None:
        """Apply the selected Text template's bounded tool policy."""
        output = getattr(plan, "output", None)
        output = output if isinstance(output, Mapping) else {}
        component_ids = output.get("component_template_ids")
        catalog = self.workflow_template_catalog()
        templates = []
        if isinstance(component_ids, list):
            templates = [catalog.get(str(item)) for item in component_ids[:8]]
            templates = [item for item in templates if isinstance(item, Mapping)]
        if not templates:
            output_type = output.get("type")
            templates = [
                item
                for item in catalog.values()
                if output_type in (item.get("result_types") or [])
            ]
        if len(templates) != 1 and not component_ids:
            return
        allowed = {
            str(tool)
            for template in templates
            for tool in (template.get("allowed_tools") or [])
        }
        unexpected = sorted(
            {str(step.tool) for step in getattr(plan, "steps", ())} - allowed
        )
        if unexpected:
            raise WorkflowTemplateError(
                "text workflow policy rejected tools: " + ", ".join(unexpected)
            )
        max_steps = sum(int(item.get("max_steps") or 0) for item in templates)
        if max_steps and len(getattr(plan, "steps", ())) > max_steps:
            raise WorkflowTemplateError(
                "text workflow policy exceeded max steps: {} > {}".format(
                    len(getattr(plan, "steps", ())), max_steps
                )
            )

    def resolve_capability_selection(
        self,
        capability_id: str,
        *,
        request_facts: Any = None,
        selection: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        del selection
        capability_id = str(capability_id or "").strip()
        text = getattr(request_facts, "text", "")
        if isinstance(request_facts, Mapping):
            text = request_facts.get("text", "")
        if capability_id == "text_analysis":
            tasks = getattr(request_facts, "tasks", None)
            if isinstance(request_facts, Mapping):
                tasks = request_facts.get("tasks")
            components = build_text_workflow_components(tasks, text)
            if len(components) >= 2:
                return {
                    "template_id": "text_analysis",
                    "template_version": "1.0.0",
                    "components": components,
                    "constraints": {},
                    "evidence": ["summary", "trace"],
                }
        if capability_id not in self.workflow_template_catalog():
            return None
        constraints = {}
        if capability_id in {"text_normalize", "text_summary", "text_stats"} and str(text or "").strip():
            constraints["text"] = str(text).strip()[:4000]
        return {"template_id": capability_id, "constraints": constraints, "evidence": []}

    def workflow_template_context(
        self,
        *,
        include_arg_shape: bool = False,
        compact: bool = True,
    ) -> Mapping[str, Any]:
        return workflow_template_context_summary(
            catalog=self.workflow_template_catalog(),
            known_tools=KNOWN_TOOL_NAMES,
            known_result_types=KNOWN_RESULT_TYPES,
            include_arg_shape=include_arg_shape,
            compact=compact,
        )

    def workflow_template_catalog(self) -> Mapping[str, Mapping[str, Any]]:
        """Return the Text-owned declarative workflow catalog."""
        return workflow_template_catalog()

    def planner_request_hint(
        self,
        request: str,
        workflow: Mapping[str, Any] | None = None,
    ) -> str:
        return workflow_request_hint(request, workflow)

    def planner_guidance(self) -> Mapping[str, Any]:
        from .planner_guidance import TEXT_PLANNER_GUIDANCE

        return TEXT_PLANNER_GUIDANCE

    def plan_policy(
        self,
        plan: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Describe the Text-owned tool policy used for this plan."""
        catalog = self.workflow_template_catalog()
        components = workflow.get("components") if isinstance(workflow, Mapping) else None
        component_ids = (
            [
                str(item.get("template_id"))
                for item in components[:8]
                if isinstance(item, Mapping) and item.get("template_id")
            ]
            if isinstance(components, list)
            else []
        )
        selected = [catalog.get(item) for item in component_ids]
        selected = [item for item in selected if isinstance(item, Mapping)]
        if selected:
            allowed_tools = list(dict.fromkeys(
                str(tool)
                for item in selected
                for tool in (item.get("allowed_tools") or [])
            ))[:32]
            return {
                "schema_version": "spatial-agent.plan-policy.v1",
                "available": True,
                "domain_id": self.domain_id,
                "policy_id": "text.workflow.composition",
                "source": "explicit_workflow",
                "selected_by": "user",
                "workflow_template_id": "text_analysis",
                "workflow_template_version": "1.0.0",
                "allowed_tools": allowed_tools,
                "max_steps": sum(int(item.get("max_steps") or 0) for item in selected),
                "result_types": [str((getattr(plan, "output", {}) or {}).get("type"))],
                "component_template_ids": component_ids,
                "candidate_policy_ids": ["text.workflow." + item for item in component_ids],
            }
        output = getattr(plan, "output", {})
        output_type = output.get("type") if isinstance(output, Mapping) else None
        candidates = [
            item
            for item in catalog.values()
            if isinstance(item, Mapping)
            and output_type in (item.get("result_types") or [])
        ]
        selected_template = candidates[0] if len(candidates) == 1 else None
        return {
            "schema_version": "spatial-agent.plan-policy.v1",
            "available": selected_template is not None,
            "domain_id": self.domain_id,
            "policy_id": (
                "text.workflow." + str(selected_template.get("id"))
                if selected_template
                else None
            ),
            "source": "domain_auto_match" if selected_template else "none",
            "selected_by": "domain" if selected_template else "none",
            "workflow_template_id": selected_template.get("id") if selected_template else None,
            "workflow_template_version": selected_template.get("version") if selected_template else None,
            "allowed_tools": list(selected_template.get("allowed_tools") or []) if selected_template else [],
            "max_steps": selected_template.get("max_steps") if selected_template else None,
            "result_types": list(selected_template.get("result_types") or []) if selected_template else [],
            "candidate_policy_ids": [str(item.get("id")) for item in candidates[:8]],
        }

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        from .request_understanding import TEXT_REQUEST_UNDERSTANDING_GUIDANCE

        return TEXT_REQUEST_UNDERSTANDING_GUIDANCE

    def clarification_details(self, request: str) -> Mapping[str, Any]:
        """Text has no spatial clarification policy."""
        return {}

    def rule_planner(self) -> Any:
        from .planner import TextSummaryPlanner

        return TextSummaryPlanner()


TEXT_DOMAIN_PACK = TextDomainPack()
