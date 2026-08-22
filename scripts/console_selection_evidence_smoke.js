/* M176: offline smoke for the shared Console Evidence Registry renderer. */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'web', 'console_evidence_registry.js'),
  'utf8'
);
const sandbox = {window: {}, console};
vm.runInNewContext(source, sandbox, {filename: 'console_evidence_registry.js'});
const renderer = sandbox.window.ConsoleEvidenceRegistry;
assert(renderer, 'Evidence Registry renderer is not exposed');

const registry = {
  schema_version: renderer.REGISTRY_SCHEMA,
  available: true,
  entry_count: 7,
  entries: [
    {id: 'result', schema_version: 'spatial-agent.result-envelope.v1', available: true, state: 'available', reference: 'result'},
    {id: 'plan_quality', schema_version: 'spatial-agent.plan-quality.v1', available: true, state: 'accepted', reference: 'result.planning.plan_quality'},
    {id: 'execution_timeline', schema_version: 'spatial-agent.execution-timeline.v1', available: true, state: 'available', reference: 'result.execution_timeline'},
    {id: 'action_lifecycle', schema_version: 'spatial-agent.action-lifecycle.v1', available: true, state: 'completed', reference: 'result.action_lifecycle'},
    {id: 'replanning', schema_version: 'spatial-agent.replanning.v1', available: false, state: 'unavailable', reference: 'result.replanning'},
    {id: 'workflow_selection', schema_version: 'spatial-agent.workflow-selection.v1', available: true, state: 'selected', reference: 'result.planning.workflow_selection'},
    {id: 'planner_selection', schema_version: 'spatial-agent.planner-selection.v1', available: true, state: 'matched', reference: 'result.planning.planner_selection'}
  ]
};
const planning = {
  workflow_selection: {
    schema_version: 'spatial-agent.workflow-selection.v1', state: 'selected',
    reason_code: 'workflow_selected', source: 'domain_discovery',
    selected_capability_id: 'text_summary', candidate_ids: ['text_summary'], candidate_count: 1
  },
  planner_selection: {
    schema_version: 'spatial-agent.planner-selection.v1', state: 'matched',
    reason_code: 'planner_matches_selected_capability', planner_kind: 'RuleBasedPlanner',
    result_type: 'text_summary_result', selected_capability_id: 'text_summary',
    planner_capability_id: 'text_summary', candidate_ids: ['text_summary']
  }
};

const readyRecovery = {
  schema_version: 'spatial-agent.evidence-recovery.v1', state: 'ready',
  reason_code: 'evidence_registry_current', action: 'none', allowed_actions: [], migratable: false
};
const full = renderer.render(planning, registry, readyRecovery);
assert(full.includes('工作流选择'), 'full projection lacks workflow selection');
assert(full.includes('规划器选择'), 'full projection lacks planner selection');
assert(full.includes('text_summary_result'), 'full projection lacks planner result type');
assert(full.includes('查看全部证据入口'), 'full projection lacks registry entries');
assert(full.includes('data-evidence-registry-state="ready"'), 'full projection lacks ready state');
assert(full.includes('data-evidence-recovery-state="ready"'), 'full projection lacks recovery state');

const compact = renderer.renderCompact(planning, registry, readyRecovery);
assert(compact.includes('工作流'), 'compact projection lacks workflow state');
assert(compact.includes('规划器'), 'compact projection lacks planner state');

const recoverable = renderer.render(planning, registry, {
  schema_version: 'spatial-agent.evidence-recovery.v1', state: 'recoverable',
  reason_code: 'evidence_registry_requires_rebuild', action: 'rebuild_from_result',
  allowed_actions: ['rebuild_from_result'], migratable: true
});
assert(recoverable.includes('可恢复'), 'recoverable state lacks Chinese label');
assert(recoverable.includes('rebuild_from_result'), 'recoverable state lacks allowed action');

const blocked = renderer.render(planning, registry, {
  schema_version: 'spatial-agent.evidence-recovery.v1', state: 'blocked',
  reason_code: 'evidence_registry_unknown_schema', action: 'reject_until_explicit_migration',
  allowed_actions: ['reject_until_explicit_migration'], migratable: false
});
assert(blocked.includes('已阻断'), 'blocked state lacks Chinese label');

const unknown = renderer.render(planning, {
  schema_version: 'spatial-agent.evidence-registry.v99',
  available: true,
  entries: [{id: 'future', schema_version: 'future.v1', reference: 'file:///private'}]
});
assert(unknown.includes('evidence_registry_unknown_schema'), 'unknown schema did not degrade');
assert(!unknown.includes('file:///private'), 'unknown registry leaked an external reference');

console.log(JSON.stringify({ok: true, fullLength: full.length, compactLength: compact.length}));
