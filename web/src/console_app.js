    const $ = id => document.getElementById(id);
    const AGENT_STAGE_DEFINITIONS = Object.freeze([
      ['发现能力', '发现'],
      ['理解请求', '理解'],
      ['生成计划', '规划'],
      ['执行任务', '执行'],
      ['汇总结果', '汇总'],
    ]);
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const rendererRegistry = window.ConsoleRendererRegistry?.create({escapeHtml});
    if (rendererRegistry && window.ConsoleGisPlugin) {
      rendererRegistry.register('map', window.ConsoleGisPlugin.createMapAdapter({
        escapeHtml,
        summaryTarget: () => $('mapSummary'),
        selectionTarget: () => $('mapSelection'),
        useSelectionButton: () => $('useMapSelection'),
        onUseSelection: context => {
          $('prompt').value = context.admin_name ? '继续分析 '+context.admin_name : '继续分析当前选中上下文';
          $('prompt').focus();
        },
      }));
    }
    function normalizeConsoleResult(data) {
      return (window.ConsoleNestedSchema && typeof window.ConsoleNestedSchema.normalize === 'function')
        ? window.ConsoleNestedSchema.normalize(data)
        : {data: data || {}, result: (data || {}).result || {}, workspace: ((data || {}).result || {}).workspace || {}, views: ((data || {}).result || {}).views || {}, invalid: true, reason: '前端嵌套契约校验模块不可用。'};
    }
    function compositeViewProjection(data) {
      const projection = data?.view || data?.result?.view;
      return projection?.schema_version === 'spatial-agent.composite-view.v1' ? projection : null;
    }
    function answerText(data) {
      const projection = compositeViewProjection(data);
      const answer = projection?.answer || {};
      if (typeof answer.summary === 'string' && answer.summary.trim()) return answer.summary;
      if (typeof answer.headline === 'string' && answer.headline.trim()) return answer.headline;
      const candidates = [data?.answer, data?.result?.answer, data?.error];
      for (const candidate of candidates) {
        if (typeof candidate === 'string' && candidate.trim()) return candidate;
        if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
          if (typeof candidate.summary === 'string' && candidate.summary.trim()) return candidate.summary;
          if (typeof candidate.headline === 'string' && candidate.headline.trim()) return candidate.headline;
        }
      }
      return statusName(data?.status);
    }
    function normalizeDecisionEvidence(data) {
      return (window.ConsoleDecisionEvidence && typeof window.ConsoleDecisionEvidence.normalize === 'function')
        ? window.ConsoleDecisionEvidence.normalize(data)
        : {status: '', visible: false, repair: {state: 'unavailable'}, rejection: {state: 'not_applicable'}, clarification: {state: 'not_applicable'}};
    }
    const DOMAIN_ROUTING_EVIDENCE_SCHEMA='spatial-agent.domain-routing-evidence.v1';
    function domainRoutingEvidenceSource(data) {
      const result=data?.result;
      if(result&&typeof result==='object'&&Object.prototype.hasOwnProperty.call(result,'domain_routing_evidence')) return {present:true,value:result.domain_routing_evidence,source:'result'};
      if(data&&typeof data==='object'&&Object.prototype.hasOwnProperty.call(data,'domain_routing_evidence')) return {present:true,value:data.domain_routing_evidence,source:'alias'};
      return {present:false,value:null,source:''};
    }
    function routingEvidenceText(value,fallback='-',limit=128) {
      const text=(typeof value==='string'||typeof value==='number')?String(value).replace(/[\u0000-\u001f\u007f]/g,' ').trim():'';
      return (text||fallback).slice(0,limit);
    }
    function normalizeDomainRoutingEvidence(data) {
      const source=domainRoutingEvidenceSource(data);
      const unavailable=reason=>({present:source.present,available:false,state:'unavailable',reason,schema_version:null,source:source.source,decision:{},lineage:{events:[]},binding:{},observability:{},candidates:[]});
      if(!source.present) return {present:false,available:false,state:'missing',reason:'',schema_version:null,source:'',decision:{},lineage:{events:[]},binding:{},observability:{},candidates:[]};
      const raw=source.value;
      if(!raw||typeof raw!=='object'||Array.isArray(raw)) return unavailable('领域路由证据不是有效对象，暂时无法安全展示。');
      if(raw.schema_version!==DOMAIN_ROUTING_EVIDENCE_SCHEMA) return unavailable(raw.schema_version?'领域路由证据使用未知 schema，暂时无法安全展示。':'领域路由证据缺少 schema，暂时无法安全展示。');
      if(raw.available!==true) return unavailable('领域路由证据不可用：'+routingEvidenceText(raw.reason_code,'未提供原因',96));
      const decision=raw.decision, lineage=raw.lineage, binding=raw.binding, observability=raw.observability;
      if(!decision||typeof decision!=='object'||!lineage||typeof lineage!=='object'||!binding||typeof binding!=='object'||!observability||typeof observability!=='object'||!Array.isArray(raw.candidates)||!Array.isArray(lineage.events)) return unavailable('领域路由证据结构不完整，暂时无法安全展示。');
      const events=lineage.events.slice(0,8).filter(item=>item&&typeof item==='object').map(item=>({
        decision_id:routingEvidenceText(item.decision_id),parent_decision_id:routingEvidenceText(item.parent_decision_id,''),status:routingEvidenceText(item.status,'unknown'),reason_code:routingEvidenceText(item.reason_code,'unknown'),selector_id:routingEvidenceText(item.selector_id,'unknown'),selected_domain_id:routingEvidenceText(item.selected_domain_id,''),selection_source:routingEvidenceText(item.selection_source,''),
      }));
      return {
        present:true,available:true,state:'available',schema_version:DOMAIN_ROUTING_EVIDENCE_SCHEMA,source:source.source,
        decision:{decision_id:routingEvidenceText(decision.decision_id),parent_decision_id:routingEvidenceText(decision.parent_decision_id,''),reason_code:routingEvidenceText(decision.reason_code,'unknown'),selector_id:routingEvidenceText(decision.selector_id,'unknown'),selected_domain_id:routingEvidenceText(decision.selected_domain_id),selection_source:routingEvidenceText(decision.selection_source,'unknown')},
        lineage:{events,root:routingEvidenceText(lineage.root_decision_id??lineage.root),current:routingEvidenceText(lineage.current_decision_id??lineage.current),truncated:lineage.truncated===true},
        binding:{state:routingEvidenceText(binding.state,'unknown'),run_id:routingEvidenceText(binding.run_id),domain_id:routingEvidenceText(binding.domain_id)},
        observability:{selector_mode:routingEvidenceText(observability.selector_mode,'unknown'),candidate_count:Number.isInteger(observability.candidate_count)?Math.max(0,observability.candidate_count):raw.candidates.length,fallback_reason:routingEvidenceText(observability.fallback_reason,''),selector_latency_ms:typeof observability.selector_latency_ms==='number'&&Number.isFinite(observability.selector_latency_ms)?Math.max(0,observability.selector_latency_ms):null},
        candidates:raw.candidates.slice(0,8).filter(item=>item&&typeof item==='object').map(item=>({domain_id:routingEvidenceText(item.domain_id)})),
      };
    }
    function renderDomainRoutingEvidence(data) {
      const model=normalizeDomainRoutingEvidence(data);
      if(!model.present) return '';
      if(!model.available) return '<div class="decision-evidence" data-domain-routing-evidence-state="unavailable"><div class="decision-evidence-head"><strong>领域路由证据</strong><span>不可用</span></div><div class="decision-evidence-grid"><section class="decision-evidence-card" data-domain-routing-evidence-card><h4>路由证据不可用</h4><p>'+escapeHtml(model.reason)+'</p></section></div></div>';
      const decision=model.decision,lineage=model.lineage,binding=model.binding,observation=model.observability;
      const parent=decision.parent_decision_id?' · 父决策 '+escapeHtml(decision.parent_decision_id):'';
      const fallback=observation.fallback_reason?' · fallback '+escapeHtml(observation.fallback_reason):'';
      const latency=observation.selector_latency_ms===null?'':' · '+escapeHtml(observation.selector_latency_ms)+' ms';
      const candidates=model.candidates.length?model.candidates.map(item=>'<code>'+escapeHtml(item.domain_id)+'</code>').join('、'):'无';
      const eventRows=lineage.events.map((item,index)=>'<li>#'+escapeHtml(index+1)+' '+escapeHtml(item.decision_id)+' · '+escapeHtml(item.status)+' · '+escapeHtml(item.reason_code)+(item.selected_domain_id?' · '+escapeHtml(item.selected_domain_id)+' / '+escapeHtml(item.selection_source):'')+'</li>').join('');
      return '<div class="decision-evidence" data-domain-routing-evidence-state="available" data-schema-version="'+DOMAIN_ROUTING_EVIDENCE_SCHEMA+'"><div class="decision-evidence-head"><strong>领域路由证据</strong><span>结构化执行绑定</span></div><div class="decision-evidence-grid"><section class="decision-evidence-card" data-domain-routing-evidence-card><h4>路由决策</h4><div>'+escapeHtml(decision.decision_id)+parent+'</div><p>'+escapeHtml(decision.reason_code)+' · '+escapeHtml(decision.selector_id)+' → '+escapeHtml(decision.selected_domain_id)+' · '+escapeHtml(decision.selection_source)+'</p></section><section class="decision-evidence-card"><h4>执行绑定与观测</h4><div>'+escapeHtml(binding.state)+' · '+escapeHtml(binding.domain_id)+' · '+escapeHtml(binding.run_id)+'</div><p>'+escapeHtml(observation.selector_mode)+' · 候选 '+escapeHtml(observation.candidate_count)+latency+fallback+'</p><p>候选领域：'+candidates+'</p></section><section class="decision-evidence-card"><h4>决策 lineage</h4><div>'+escapeHtml(lineage.root)+' → '+escapeHtml(lineage.current)+' · '+escapeHtml(lineage.events.length)+' 个事件'+(lineage.truncated?' · 已截断':'')+'</div>'+(eventRows?'<ul>'+eventRows+'</ul>':'<p>没有可读 lineage 事件。</p>')+'</section></div></div>';
    }
    function renderDecisionEvidence(data) {
      const routingHtml=renderDomainRoutingEvidence(data);
      const html=(window.ConsoleDecisionEvidence && typeof window.ConsoleDecisionEvidence.render === 'function')?(window.ConsoleDecisionEvidence.render(data).html||''):'';
      return html+routingHtml;
    }
    function dockWorkspaceControls() {
      const controls = $('workspaceControls');
      const chat = $('chatPanel');
      const chatHead = chat?.querySelector('.chat-head');
      if (controls && chat && chatHead && controls.parentElement !== chat) {
        controls.className = 'chat-settings';
        chatHead.insertAdjacentElement('afterend', controls);
      }
    }
    dockWorkspaceControls();
     function setResultPanel(selector, visible) { document.querySelectorAll(selector).forEach(panel => panel.classList.toggle('is-visible', visible)); }
     function setAdvancedVisibility(visible, summary, expand) { const details=$('advancedResults'); if(!details) return; details.hidden=!visible; if(summary) $('advancedSummary').textContent=summary; if(typeof expand==='boolean') details.open=expand; }
     function resetResultWorkspace(reason='reset') {
       stopLiveRun();
       rendererRegistry?.reset({reason,generation:conversationGeneration,surfaces:{generic:$('genericResult'),visual:$('map')}});
      $('resultEmpty').style.display = 'flex';
      setResultPanel('.result-panel', false);
      $('planPreview').innerHTML = '点击“预览计划”查看工具 DAG；预览不会执行工具。';
      $('workflowEvidenceWorkspace').innerHTML = '';
      $('genericResult').textContent = '';
      $('map').textContent = '';
      $('decisionEvidence').innerHTML = '';
      $('evidenceSummary').innerHTML = '';
      $('geometryEvidenceDetail').innerHTML = '';
      $('lineageEvidence').innerHTML = '';
      $('provenanceEvidence').innerHTML = '';
      $('runtimeEvidence').innerHTML = '';
      $('selectionEvidence').innerHTML = '';
      $('dataEvidence').innerHTML = '';
      $('releaseEvidence').innerHTML = '';
      $('memoryEvidence').innerHTML = '';
      $('degradationEvidence').innerHTML = '';
      setAdvancedVisibility(false);
      lastRunData = null;
      $('geometryEvidence').textContent = '';
      $('answerProjection').innerHTML = '';
      $('answerProjection').hidden = true;
    }
    function updateResultPanels(data) {
      const contract=normalizeConsoleResult(data);
      data=contract.data;
      geometryEvidence(data);
      const hasRun = Boolean(data.run_id || data.status);
      const envelope=data.result||{};
      const status=String(data.status||'').toUpperCase();
      const plannerMetrics=data.planner_metrics||{};
      const hasMetrics=Boolean(plannerMetrics.model||plannerMetrics.wire_api||plannerMetrics.latency_ms||plannerMetrics.usage);
      const stepsData=Array.isArray(data.steps)?data.steps:[];
      const provenanceData=data.provenance||{};
      const hasProvenance=Boolean(provenanceData.execution_policy||(Array.isArray(provenanceData.steps)&&provenanceData.steps.length));
      const hasTrace=Array.isArray(data.trace_summary)&&data.trace_summary.length>0;
      const hasEvidence=Boolean(data.evidence||data.evidence_registry||data.plan_evidence||data.runtime_context||data.artifact_ref||data.artifacts||envelope.evidence_registry||envelope.lineage||envelope.geometry);
      $('resultEmpty').style.display = hasRun ? 'none' : 'flex';
      setResultPanel('.common-result', false);
      setResultPanel('.answer-result', hasRun);
      setResultPanel('.metrics-result', hasMetrics);
      setResultPanel('.steps-result', stepsData.length>0);
      setResultPanel('.provenance-result', hasProvenance);
      setResultPanel('.trace-result', hasTrace);
      setResultPanel('.evidence-result', hasEvidence);
      const hasDecisionEvidence=hasRun && (normalizeDecisionEvidence(data).visible||domainRoutingEvidenceSource(data).present);
      setResultPanel('.decision-evidence-result', hasDecisionEvidence);
      setResultPanel('.generic-result', false);
      setResultPanel('.map-result', false);
      const hasAdvanced=Boolean(hasEvidence||hasProvenance||hasTrace||stepsData.length||hasDecisionEvidence);
      setAdvancedVisibility(hasAdvanced, hasAdvanced?'计划、证据和执行轨迹':'暂无高级执行详情', false);
    }
    function scopedReference(ref,domainId=currentDomainId()) { const text=String(ref||''); return text.startsWith('/domains/')?text:(text.startsWith('/')?domainPath(text,domainId):text); }
    function artifactReferencePath(reference,legacyRef,kind,domainId=currentDomainId()) { const direct=reference?.access?.path; if(typeof direct==='string'&&direct.startsWith('/domains/')) return direct; if(typeof direct==='string'&&direct.startsWith('/artifacts/')) return domainPath(direct,domainId); const name=String(reference?.ref||legacyRef||'').split(/[\\/]/).pop(); return name?domainPath('/artifacts/'+encodeURIComponent(kind)+'/'+encodeURIComponent(name),domainId):''; }
    function geometryArtifactPath(reference, legacyRef, domainId) { return artifactReferencePath(reference,legacyRef,'geojson',domainId); }
    function renderAsyncResultEvidence(data) { const evidence=(data.async_observability||{}).result_evidence; if(!evidence||!evidence.schema_version) return ''; const labels={pending:'处理中',success:'可用',degraded:'部分可用',unavailable:'不可用'}; const panels=Object.entries((evidence.views||{}).panels||{}).slice(0,12).map(([id,panel])=>escapeHtml(id)+'：'+escapeHtml(panel.state||'unknown')).join(' · '); const model=evidence.model_evidence||{}; const modelText=model.schema_version?' · 模型 '+escapeHtml(model.execution_mode||'unknown')+(model.provider?' / '+escapeHtml(model.provider):'')+(model.model?' / '+escapeHtml(model.model):'')+(model.fixture_id?' / '+escapeHtml(model.fixture_id):''):''; const interaction=evidence.interaction||{}; const selectionHtml=window.ConsoleEvidenceRegistry?.renderCompact?window.ConsoleEvidenceRegistry.renderCompact(evidence.planning,evidence.evidence_registry,evidence.evidence_recovery):''; return '<div class="execution-evidence async-result-evidence"><strong>异步结果证据</strong> · '+escapeHtml(labels[evidence.state]||evidence.state||'未知')+' · '+escapeHtml(evidence.result_type||'unknown')+modelText+(selectionHtml?' · '+selectionHtml:'')+(interaction.state?' · 下一步 '+escapeHtml(interaction.state):'')+(panels?' · '+panels:'')+(evidence.artifact?.available?' · artifact 可恢复':'')+'</div>'; }
    function renderActionTimeline(data) { const envelope=data.result||{}; const timeline=envelope.execution_timeline||data.execution_timeline||{}; const actions=(timeline.events||[]).filter(item=>item&&item.kind==='action').slice(0,8); if(!actions.length) return ''; const impactLabels={result_attached:'结果已关联',state_changed:'状态已改变',no_change:'无状态变化',none:'无结果影响',unknown:'影响未知'}; const items=actions.map(item=>{ const linkage=item.action_linkage||{}; const identity=linkage.identity_linkage||{}; const pre=linkage.preconditions||{}; const lineage=linkage.transition_lineage||{}; const effect=linkage.effect||{}; const preText=pre.state&&pre.state!=='unknown'?' · 前置条件 '+escapeHtml(pre.state):''; const lineageText=Number(lineage.event_count||0)>1?' · 连续动作 '+escapeHtml(lineage.event_count)+' 步':''; const effectText=effect.impact&&effect.impact!=='unknown'?' · 影响 '+escapeHtml(impactLabels[effect.impact]||effect.impact):''; return escapeHtml(linkage.action_id||'unknown')+'：'+escapeHtml(statusName(linkage.status||'UNKNOWN'))+(identity.available?' · 身份已关联':' · 身份不可用')+preText+effectText+lineageText; }).join(' · '); return '<div class="execution-evidence action-timeline"><strong>动作时间线</strong> · '+items+'</div>'; }
    function renderExecutionRecord(data) { const record=data.execution_record||(data.result||{}).execution_record||{}; const asyncEvidence=renderAsyncResultEvidence(data); const actionTimeline=renderActionTimeline(data); if(!record.schema_version) return actionTimeline+asyncEvidence; const envelope=data.result||{}; const context=data.runtime_context||envelope.runtime_context||{}; const provider=context.tool_provider||{}; const model=envelope.model_evidence||{}; const deployment=envelope.deployment_evidence||{}; const deploymentData=deployment.data||{}; const degradation=deployment.degradation||{}; const contextText=context.schema_version?' · 领域 '+escapeHtml(context.domain_id||record.domain_id||'unknown')+' · Planner '+escapeHtml(context.planner||'unknown')+' · Backend '+escapeHtml(context.backend||'unknown')+' · Provider '+escapeHtml(provider.id||'unknown')+' · Context '+escapeHtml(context.schema_version)+(context.fingerprint?' · 指纹 '+escapeHtml(String(context.fingerprint).slice(0,19)):''):''; const modelText=model.schema_version?' · 模型 '+escapeHtml(model.execution_mode||'unknown')+(model.model?' / '+escapeHtml(model.model):'')+(model.fixture_id?' / '+escapeHtml(model.fixture_id):''):''; const deploymentText=deployment.schema_version?' · 部署证据 '+escapeHtml(deployment.status||'unknown')+' · 数据 '+escapeHtml(deploymentData.runtime_readiness||deploymentData.runtime_status||'unknown')+' · 降级 '+escapeHtml(degradation.status||'none'):''; const releaseRef=(envelope.lineage||{}).release_evidence?.ref||''; const releaseText=releaseRef?' · <a href="'+escapeHtml(scopedReference(releaseRef,responseDomain(data)))+'" target="_blank">发布证据</a>':''; const reused=record.idempotency_reused?' · 幂等结果复用':''; return actionTimeline+asyncEvidence+'<div class="execution-evidence"><strong>统一执行记录</strong> · '+escapeHtml(record.kind||'unknown')+' · '+escapeHtml(statusName(record.status||'UNKNOWN'))+' · '+escapeHtml(record.domain_id||'unknown')+' · 轨迹 '+escapeHtml(record.trace_count??0)+' 条 · artifact '+escapeHtml(record.artifact_available?'可恢复':'未导出')+escapeHtml(reused)+contextText+modelText+deploymentText+releaseText+'</div>'; }
    function renderActionEvidence(data) { const envelope=data.result||{}; const execution=data.action_execution||envelope.action_execution||{}; const actionId=data.action_id||envelope.action?.id; if(!actionId) return ''; const executionId=data.action_execution_id||envelope.lineage?.action_execution?.ref||''; const domainId=responseDomain(data,domainForAction(executionId)); if(executionId) actionDomains.set(String(executionId),domainId); const status=data.status||execution.status||'UNKNOWN'; const reused=data.idempotency_reused===true?' · 幂等结果复用':''; const artifactPath=artifactReferencePath(envelope.artifacts?.action||data.artifact_reference||execution.artifact_reference,data.artifact_ref,'actions',domainId); const links=[]; if(executionId) links.push('<a href="'+escapeHtml(domainPath('/action-executions/'+encodeURIComponent(executionId),domainId))+'" target="_blank">恢复执行证据</a>'); if(artifactPath) links.push('<a href="'+escapeHtml(artifactPath)+'" target="_blank">打开 Action artifact</a>'); const traceItems=(data.trace_summary||[]).slice(0,4).map(item=>'<li>'+escapeHtml(item)+'</li>').join(''); return '<div class="action-evidence"><div class="action-evidence-head"><strong>Action 执行证据</strong><span class="step-status '+String(status).toLowerCase()+'">'+escapeHtml(statusName(status))+'</span><span>'+escapeHtml(actionId)+'</span></div><div class="action-evidence-meta">执行 ID：'+escapeHtml(executionId||'-')+' · 领域：'+escapeHtml(domainId||'-')+' · 耗时：'+escapeHtml(execution.duration_ms??'-')+' 毫秒'+escapeHtml(reused)+'</div>'+(links.length?'<div class="action-evidence-links">'+links.join('')+'</div>':'')+(traceItems?'<ol class="action-trace">'+traceItems+'</ol>':'')+'</div>'; }
    function scopeWorkspaceArtifactLinks(data) { const domainId=responseDomain(data); $('genericResult').querySelectorAll('a[href^="/artifacts/"]').forEach(link=>link.setAttribute('href',domainPath(link.getAttribute('href'),domainId))); }
    function genericResult(data) { const contract=normalizeConsoleResult(data); const safeData=contract.data; const projection=compositeViewProjection(safeData); const workspace=(safeData.result||{}).workspace||{}; const projected=projection&&rendererRegistry?.projectionToPanels?rendererRegistry.projectionToPanels(projection):null; const technicalHtml=renderExecutionRecord(safeData)+renderActionEvidence(safeData); const prefixHtml=technicalHtml?'<details class="technical-inline"><summary>运行信息（高级）</summary>'+technicalHtml+'</details>':''; if(!rendererRegistry){ setResultPanel('.generic-result',true); $('resultEmpty').style.display='none'; $('genericResult').className='structured-view'; $('genericResult').innerHTML=prefixHtml+'<div class="error">Renderer Registry 不可用，结构化 view 已安全降级。</div>'; scopeWorkspaceArtifactLinks(safeData); return Promise.resolve({status:'unavailable'}); } $('genericResult').className='structured-view'; return rendererRegistry.renderWorkspace({panels:projected?.panels||resultViewPanels(safeData),specs:projected?.specs||workspace.view_specs||[],declaredPanels:projected?.declaredPanels||workspace.panels||[],run:safeData,prefixHtml,surfaces:{generic:$('genericResult'),visual:$('map')},onSurface:(surface,visible)=>{ if(surface==='generic') { setResultPanel('.generic-result',visible); if(visible) $('resultEmpty').style.display='none'; } if(surface==='visual') { setResultPanel('.map-result',visible); if(visible) $('resultEmpty').style.display='none'; } }}).then(report=>{ scopeWorkspaceArtifactLinks(safeData); $('genericResult').querySelectorAll('[data-run-id]').forEach(button=>button.addEventListener('click',()=>openRunDetail(button.getAttribute('data-run-id')))); return report; }).catch(error=>{ setResultPanel('.generic-result',true); $('resultEmpty').style.display='none'; $('genericResult').innerHTML=prefixHtml+'<div class="error">结构化 view 渲染失败：'+escapeHtml(error.message)+'</div>'; scopeWorkspaceArtifactLinks(safeData); return {status:'failed'}; }); }
    function resultViewPanels(data) { const safe=normalizeConsoleResult(data); const views=(safe.result||{}).views||{}; return (views.panels)||{}; }
    function planDagFromPlan(plan) {
      const nodes=(plan?.steps||[]).map(step=>({id:step.id,tool:step.tool,depends_on:step.depends_on||[],arg_keys:Object.keys(step.args||{})}));
      return {nodes,edges:nodes.flatMap(node=>(node.depends_on||[]).map(source=>({from:source,to:node.id})))};
    }
    function shortFingerprint(value) {
      const text=String(value||'');
      return text.length>30?text.slice(0,20)+'…'+text.slice(-8):text;
    }
    function planIdentityText(data) {
      const envelope=data.result||{};
      const planEvidence=data.plan_evidence||envelope.planning||{};
      const identity=data.plan_identity||planEvidence.plan_identity||{};
      const parts=[];
      if(identity.version) parts.push(identity.version);
      if(identity.fingerprint) parts.push(shortFingerprint(identity.fingerprint));
      if(planEvidence.plan_fingerprint_match===true) parts.push('预览匹配：是');
      else if(planEvidence.plan_fingerprint_match===false) parts.push('预览匹配：否');
      else if(identity.fingerprint) parts.push('预览匹配：未绑定');
      return parts.join(' · ');
    }
    function planIdentitySummary(data) {
      const text=planIdentityText(data);
      return text?'<div class="distribution-note">计划身份：'+escapeHtml(text)+'</div>':'';
    }
    function renderPlanDag(data, expand=false) {
      const plan=data.plan||{};
      const dag=data.dag||planDagFromPlan(plan);
      const nodes=Array.isArray(dag.nodes)?dag.nodes:[];
      const status=data.status||'PLANNED';
      const exact=(data.plan_evidence||{}).exact_template_ids||[];
      const source=(data.plan_evidence||{}).source||'未知';
      const summary=nodes.length?'共 '+nodes.length+' 个节点 · '+(dag.edges||[]).length+' 条依赖':'无工具节点（直接回答或等待澄清）';
      $('resultEmpty').style.display='none';
      $('planPreview').innerHTML='<div class="plan-preview-head"><span class="plan-preview-status">'+escapeHtml(statusName(status))+'</span><small>'+escapeHtml(summary)+'</small></div><div class="muted">'+escapeHtml(plan.goal||data.error||'尚未生成任务计划。')+'</div>'+(exact.length?'<div class="distribution-note">模板：'+escapeHtml(exact.join('、'))+' · 来源：'+escapeHtml(source)+'</div>':'')+planIdentitySummary(data)+'<div class="plan-dag">'+nodes.map(node=>'<div class="plan-dag-node"><strong>'+escapeHtml(node.id)+' · '+escapeHtml(node.tool)+'</strong><small>依赖：'+escapeHtml((node.depends_on||[]).join('、')||'无')+' · 参数：'+escapeHtml((node.arg_keys||[]).join('、')||'无')+'</small></div>').join('')+'</div>';
      setResultPanel('.plan-preview-result', true);
      setAdvancedVisibility(true, '计划预览 · 不会执行工具', expand);
    }
    function renderPlanPreview(data, expand=false) {
      if(data&&((data.plan&&data.plan.steps)||data.dag||data.error)) renderPlanDag(data, expand);
      renderWorkflowEvidence(data||{});
    }
    function renderWorkflowEvidence(data) {
      const renderer=window.ConsoleWorkflowEvidence;
      const html=renderer&&typeof renderer.render==='function'?renderer.render(data):'';
      $('workflowEvidenceWorkspace').innerHTML=html;
      if(html) $('resultEmpty').style.display='none';
      setResultPanel('.workflow-evidence-result',Boolean(html));
      if(html) setAdvancedVisibility(true, '计划、工作流和执行详情', undefined);
    }
    async function previewPlan() {
      const request=$('prompt').value.trim();
      if(!request) return;
      const domainId=currentDomainId();
      const button=$('previewPlan');
      button.disabled=true;
      try {
        validateSelection(request);
        const workflow=await validateWorkflowSelection();
        const domainContext=rendererRegistry?.context()||{};
        const payload=withDomainPayload(Object.assign({request,session_id:$('session').value,planner:$('planner').value,backend:$('backend').value,workflow},domainContext),domainId);
        const response=await nativeFetch(domainPath('/runs/preview',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const data=await response.json();
        if(!response.ok) throw new Error(responseError(data,'计划预览失败'));
        lastPlanPreview={request,session_id:$('session').value,domain_id:domainId,planner:$('planner').value,backend:$('backend').value,workflow:JSON.stringify(workflow||null),domain_context:JSON.stringify(domainContext),fingerprint:data.plan_identity?.fingerprint};
        renderPlanPreview(data, true);
        setStatus(data.status);
      } catch(error) {
        $('planPreview').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>';
        setResultPanel('.plan-preview-result', true);
      } finally {
        button.disabled=false;
      }
    }
     let lastRunData = null;
     let lastPlanPreview = null;
     let runtimeEvidenceSnapshot = null;
     let runtimeEvidencePromise = null;
     let conversationGeneration = 0;
     let liveRunConsumer = null;
     let liveRunTicker = null;
     let liveRunDetailTimer = null;
     const liveRunState = {runId:'',domainId:'',request:'',startedAt:0,lastEventAt:0,lastSequence:0,eventCount:0,currentPhase:'',currentAction:'',transport:'',answerBuffer:'',answerStream:null,answerMessage:null,finalizing:false,detailPolling:false,runElapsedMs:null,phaseElapsedMs:null,runRemainingMs:null,phaseRemainingMs:null,budgetState:'',heartbeatCount:0,retryCount:0,recoveryAction:''};
     let activeRunId = null;
     let activeRunDomainId = null;
     let activeRunParams = {};
     resetResultWorkspace();
    let workflowTemplates = {};
    let actionCatalog = {schema_version:'spatial-agent.actions.v1',domain_id:'unknown',actions:[]};
    let actionCatalogPromise = null;
    let domainCatalog = {domains:[]};
    let legacyRouting = false;
    let domainGeneration = 0;
    let autoDomainBinding = null;
    let autoDraftSessionId = '';
    const LEGACY_DOMAIN_VALUE = '__legacy__';
    const AUTO_DOMAIN_VALUE = 'auto';
    const AUTO_BINDING_STORAGE_KEY = 'spatial-agent.console.auto-binding';
    const runDomains = new Map();
    const actionDomains = new Map();
    const decisionDomains = new Map();
    const sessionDomains = new Map();
    const localDraftSessionIds = new Set();
    const domainRoutingRequests = new Map();
    let sessionCatalogGeneration = 0;
    const nativeFetch = window.fetch.bind(window);
    const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
    function selectedDomainModeId() { return $('domain').value||LEGACY_DOMAIN_VALUE; }
    function usesAutoRouting() { return selectedDomainModeId()===AUTO_DOMAIN_VALUE; }
    function currentDomainId() { return usesAutoRouting()?(autoDomainBinding?.domain_id||AUTO_DOMAIN_VALUE):selectedDomainModeId(); }
    function usesLegacyRouting(domainId=currentDomainId()) { return legacyRouting||!domainId||domainId===LEGACY_DOMAIN_VALUE; }
    function domainPath(path,domainId=currentDomainId()) { const clean=String(path||'').startsWith('/')?String(path):'/'+String(path||''); if(clean.startsWith('/domains/')||usesLegacyRouting(domainId)) return clean; return '/domains/'+encodeURIComponent(domainId)+clean; }
    function withDomainPayload(payload,domainId=currentDomainId()) { const result=Object.assign({},payload||{}); if(!usesLegacyRouting(domainId)&&domainId!==AUTO_DOMAIN_VALUE) result.domain_id=domainId; return result; }
    function responseError(data,fallback) { const detail=data?.detail; if(typeof data?.error==='string') return data.error; if(typeof detail==='string') return detail; if(detail&&typeof detail==='object') return detail.message||detail.error||detail.code||fallback; return fallback; }
    function responseDomain(data,fallback=currentDomainId()) { if(usesLegacyRouting(fallback)) return fallback; return data?._console_domain_id||data?.domain_id||data?.runtime_context?.domain_id||data?.result?.runtime_context?.domain_id||data?.execution_record?.domain_id||fallback; }
    function rememberRunDomain(data,fallback=currentDomainId()) { const domainId=responseDomain(data,fallback); if(data?.run_id&&domainId) runDomains.set(String(data.run_id),domainId); const decisionId=data?.decision_evidence?.decision_id||data?.result?.decision?.decision_id; if(decisionId&&domainId) decisionDomains.set(String(decisionId),domainId); return domainId; }
    function domainForRun(runId,fallback=currentDomainId()) { return runDomains.get(String(runId||''))||lastRunData?.run_id===runId&&responseDomain(lastRunData,fallback)||fallback; }
    function domainForAction(executionId,fallback=currentDomainId()) { return actionDomains.get(String(executionId||''))||fallback; }
    function persistSelectedDomain(domainId=selectedDomainModeId()) { try { window.localStorage.setItem('spatial-agent.console.domain',domainId); } catch(error) { /* Storage can be disabled without disabling the Console. */ } }
    function preferredDomainId() { try { return window.localStorage.getItem('spatial-agent.console.domain')||''; } catch(error) { return ''; } }
    function persistAutoDomainBinding() { try { if(autoDomainBinding?.domain_id&&autoDomainBinding?.session_id) window.localStorage.setItem(AUTO_BINDING_STORAGE_KEY,JSON.stringify(autoDomainBinding)); else window.localStorage.removeItem(AUTO_BINDING_STORAGE_KEY); } catch(error) { /* Storage can be disabled without disabling the Console. */ } }
    function preferredAutoDomainBinding(availableDomains) { try { const value=JSON.parse(window.localStorage.getItem(AUTO_BINDING_STORAGE_KEY)||'null'); if(!value?.domain_id||!value?.session_id||!availableDomains.has(String(value.domain_id))) return null; return {domain_id:String(value.domain_id),session_id:String(value.session_id)}; } catch(error) { return null; } }
    function setCancelState(active) { $('cancelRun').hidden=!active; $('cancelRun').disabled=false; }
    async function cancelActiveRun() { if(!activeRunId) return; const runId=activeRunId,domainId=activeRunDomainId||domainForRun(runId); $('cancelRun').disabled=true; try { const body=withDomainPayload({planner:activeRunParams.planner||'rule',backend:activeRunParams.backend||'memory'},domainId); const response=await nativeFetch(domainPath('/runs/'+encodeURIComponent(runId)+'/cancel',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); if(!response.ok) throw new Error(responseError(await response.json().catch(()=>({})),'取消请求失败')); } catch(error) { $('error').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>'; $('cancelRun').disabled=false; } }
    function bindAutoDomain(data,fallbackDomain='') {
      if(!usesAutoRouting()) return '';
      const domainId=data?.domain_id||data?.selection?.domain_id||data?.domain_selection?.domain_id||fallbackDomain;
      if(!domainId||domainId===AUTO_DOMAIN_VALUE) return '';
      const sessionId=data?.session_id||autoDomainBinding?.session_id||autoDraftSessionId||'';
      autoDomainBinding={domain_id:String(domainId),session_id:String(sessionId||'')};
      if(sessionId) autoDraftSessionId=String(sessionId);
      persistAutoDomainBinding();
      if(sessionId){ addConversationOption({session_id:sessionId,display_name:selectedConversationLabel()},domainId); $('session').value=sessionId; }
      return String(domainId);
    }
    function ensureAutoDraftSessionId() {
      if(autoDomainBinding?.session_id) return autoDomainBinding.session_id;
      if(autoDraftSessionId) return autoDraftSessionId;
      const identity=globalThis.crypto?.randomUUID?.()||String(Date.now())+'-'+Math.random().toString(16).slice(2);
      autoDraftSessionId='conversation-auto-'+String(identity).replace(/[^A-Za-z0-9_-]/g,'').slice(0,64);
      localDraftSessionIds.add(autoDraftSessionId);
      return autoDraftSessionId;
    }
     async function pollQueuedRun(queued,payload,runDomain) {
      rememberRunDomain(queued,runDomain);
      activeRunId=queued.run_id;
      activeRunDomainId=runDomain;
      activeRunParams=payload;
      setCancelState(true);
      let data=queued;
      for(let attempt=0; attempt<600 && ['QUEUED','PLANNING','EXECUTING'].includes(data.status); attempt++) {
        await sleep(250);
        const response=await nativeFetch(domainPath('/runs/'+encodeURIComponent(queued.run_id),runDomain)+'?planner='+encodeURIComponent(payload.planner||'rule')+'&backend='+encodeURIComponent(payload.backend||'memory'));
        if(response.ok) {
          data=await response.json();
          rememberRunDomain(data,runDomain);
          if(data.status) {
            setStatus(data.status);
            const progress={QUEUED:'已进入运行队列，等待运行时接管。',PLANNING:'正在理解请求并生成任务计划。',EXECUTING:'正在调用工具并组合结构化结果。'}[String(data.status).toUpperCase()];
            if(progress) $('subtitle').textContent=progress;
          }
        }
      }
      if(activeRunId===queued.run_id) { activeRunId=null; activeRunDomainId=null; activeRunParams={}; setCancelState(false); }
       return data;
     }
     function liveRunIsTerminal(data) { return ['COMPLETED','PARTIAL','FAILED','REJECTED','BLOCKED','CANCELLED','TIMED_OUT'].includes(String(data?.status||'').toUpperCase()); }
     function runEventsPath(runId,domainId) { return domainPath('/runs/'+encodeURIComponent(runId)+'/events',domainId); }
     async function fetchLiveRunDetail(runId,domainId) {
       for(let attempt=0;attempt<4;attempt++) {
         try {
           const response=await nativeFetch(domainPath('/runs/'+encodeURIComponent(runId),domainId)+'?planner='+encodeURIComponent(activeRunParams.planner||$('planner').value||'rule')+'&backend='+encodeURIComponent(activeRunParams.backend||$('backend').value||'memory'),{cache:'no-store'});
           if(response.ok) return await response.json();
         } catch(_) { /* A later bounded attempt may observe the persisted terminal result. */ }
         if(attempt<3) await sleep(120);
       }
       return null;
     }
     async function finishLiveRun(event,providedData) {
       if(liveRunState.finalizing||!liveRunState.runId) return;
       liveRunState.finalizing=true;
       const runId=liveRunState.runId,domainId=liveRunState.domainId;
       const data=providedData||await fetchLiveRunDetail(runId,domainId);
       if(!data) {
         liveRunState.finalizing=false;
         $('liveRunAction').textContent='运行已结束，但最终结果暂时无法读取。';
         $('error').innerHTML='<div class="error">运行已结束，最终结果读取失败；请稍后从历史任务恢复。</div>';
         return;
       }
       liveRunState.lastEventAt=Date.now();
       liveRunState.currentPhase='evidence';
       liveRunState.currentAction=liveRunIsTerminal(data)?'最终结果已写入，可查看结构化结果。':'正在读取最终结果。';
       const finalAnswer=answerText(data)||'运行已结束。';
       if(liveRunState.answerStream) await liveRunState.answerStream.finish(finalAnswer);
       else renderLiveAssistantMessage(finalAnswer);
       const hasLiveAssistantMessage=completeLiveAssistantMessage(runId);
       stopLiveRun({preserve:true});
       if(activeRunId===runId){ activeRunId=null; activeRunDomainId=null; activeRunParams={}; setCancelState(false); }
       if(runId===liveRunState.runId&&domainId===currentDomainId()&&conversationGeneration>=0){
         rememberRunDomain(data,domainId);
         renderRun(data);
         if(!liveRunState.finalAnswerShown){ if(!hasLiveAssistantMessage) appendMessage('assistant',finalAnswer,runId); liveRunState.finalAnswerShown=true; }
       }
       refreshLiveSummary();
       liveRunState.finalizing=false;
     }
     function startRunDetailFallback(runId,domainId) {
       if(liveRunState.detailPolling||liveRunState.runId!==String(runId)) return;
       liveRunConsumer?.stop?.(); liveRunConsumer=null;
       liveRunState.detailPolling=true; liveRunState.transport='polling';
       liveRunState.currentAction='实时事件暂不可用，已切换为状态轮询。'; refreshLiveSummary();
       const poll=async()=>{
         if(liveRunState.runId!==String(runId)||liveRunState.finalizing){ liveRunState.detailPolling=false; return; }
         try {
           const data=await fetchLiveRunDetail(runId,domainId);
           if(data){
             lastRunData=data;
             if(data.status) setStatus(data);
             if(liveRunIsTerminal(data)){ liveRunState.detailPolling=false; await finishLiveRun(null,data); return; }
             liveRunState.lastEventAt=Date.now(); liveRunState.currentAction='运行状态：'+statusName(data.status||'处理中'); refreshLiveSummary();
           }
         } catch(_) { /* Keep the bounded fallback alive while the worker is running. */ }
         if(liveRunState.detailPolling) liveRunDetailTimer=window.setTimeout(poll,900);
       };
       poll();
     }
     function startLiveRun(data,request,domainId) {
       const runId=String(data?.run_id||'');
       if(!runId) return false;
       stopLiveRun();
       liveRunState.runId=runId; liveRunState.domainId=domainId; liveRunState.request=request||''; liveRunState.startedAt=Date.now(); liveRunState.lastEventAt=Date.now(); liveRunState.lastSequence=0; liveRunState.eventCount=0; liveRunState.currentPhase='resolve'; liveRunState.currentAction='已接收请求，等待运行时接管。'; liveRunState.transport=''; liveRunState.answerBuffer=''; liveRunState.answerMessage=createLiveAssistantMessage(runId); liveRunState.answerStream=window.ConsoleAnswerStream?.create?.({onText:text=>{ if(liveRunState.runId!==runId) return; liveRunState.answerBuffer=text; $('answer').textContent=text; $('answer').className='answer'; renderLiveAssistantMessage(text); }}); liveRunState.finalizing=false; liveRunState.finalAnswerShown=false;
       activeRunId=runId; activeRunDomainId=domainId; activeRunParams={planner:$('planner').value,backend:$('backend').value}; setCancelState(true);
       renderLiveRunShell(data,request);
       liveRunTicker=window.setInterval(refreshLiveSummary,1000);
       if(!window.ConsoleRunEvents?.create){ startRunDetailFallback(runId,domainId); return true; }
       liveRunConsumer=window.ConsoleRunEvents.create({
         runId,
         eventsPath:()=>runEventsPath(runId,domainId),
         after:0,
         onEvent:handleLiveEvent,
         onTransport:info=>{ liveRunState.transport=info.transport||''; if(info.transport==='polling') liveRunState.currentAction='实时连接不可用，正在使用轮询获取事件。'; refreshLiveSummary(); },
         onOpen:()=>{ liveRunState.currentAction='已连接实时事件流，等待下一阶段。'; refreshLiveSummary(); },
         onError:info=>{ if(info?.transport==='sse') liveRunState.currentAction='实时连接中断，正在尝试轮询恢复。'; else liveRunState.currentAction='事件读取暂时失败，正在重试。'; refreshLiveSummary(); },
         onUnavailable:()=>startRunDetailFallback(runId,domainId),
         onComplete:event=>finishLiveRun(event),
       });
       liveRunConsumer.start();
       return true;
     }
     window.fetch = async (input, init) => {
      const payload=init?.body&&typeof init.body==='string'?JSON.parse(init.body||'{}'):{};
      const submittedDomain=payload.domain_id||currentDomainId();
      if(input==='/runs/auto' && init?.method==='POST') {
        const routingResponse=await nativeFetch('/runs/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if(!routingResponse.ok) return routingResponse;
        let data=await routingResponse.json();
        const runDomain=data?.domain_id;
         if(runDomain&&data?.run_id) {
           bindAutoDomain(data,runDomain);
           rememberRunDomain(data,runDomain);
         }
        return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
      }
      if(input===domainPath('/runs',submittedDomain) && init?.method==='POST') {
        const queuedResponse=await nativeFetch(domainPath('/runs/async',submittedDomain),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(withDomainPayload(payload,submittedDomain))});
        if(!queuedResponse.ok) return queuedResponse;
         const queued=await queuedResponse.json();
         if(usesAutoRouting()) bindAutoDomain(queued,submittedDomain);
         return new Response(JSON.stringify(queued),{status:200,headers:{'Content-Type':'application/json'}});
      }
      return nativeFetch(input,init);
    };
       const statusNames={IDLE:'待机',SUBMITTED:'已提交',QUEUED:'排队中',RUNNING:'运行中',PLANNING:'规划中',PLANNED:'计划已生成',EXECUTING:'执行中',WAITING_FOR_DECISION:'等待确认',COMPLETED:'已完成',NEEDS_CLARIFICATION:'等待澄清',REJECTED:'已拒绝',FAILED:'失败',BLOCKED:'已阻塞',CANCELLED:'已取消',TIMED_OUT:'已超时'};
    const errorCategoryLabels={provider:'模型服务错误',planning:'规划错误',tool:'工具执行错误',timeout:'执行超时',invalid_input:'无效输入',execution:'执行错误',cancelled:'已取消',rejected:'请求已拒绝',clarification:'需要澄清'};
    function failureEvidenceBadge(failure) { if(!failure) return ''; const phase=String(failure.phase||'unknown'); const code=String(failure.code||'unknown'); const retryable=failure.retryable===true?'可重试':'不可重试'; return '<span class="failure-evidence" title="版本化失败证据：'+escapeHtml(String(failure.schema_version||''))+'">阶段：'+escapeHtml(phase)+' · 错误码：'+escapeHtml(code)+' · '+retryable+'</span>'; }
    function errorCategoryBadge(category) { if(!category) return ''; const key=String(category).toLowerCase(); const failure=(typeof lastRunData!=='undefined'&&lastRunData)?(lastRunData.failure||(lastRunData.result||{}).failure):null; return '<span class="error-category '+key+'" title="结构化错误分类：'+escapeHtml(key)+'">'+escapeHtml(errorCategoryLabels[key]||category)+'</span>'+failureEvidenceBadge(failure); }
    let health={capabilities:{}};
    const statusName=value=>statusNames[value]||value;
     function agentStageStates(value) {
       const data=value&&typeof value==='object'?value:{};
       const status=String(data.status||value||'IDLE').toUpperCase();
       const phase=String(data.phase||'').toLowerCase();
       const clarification=data.clarification||data.result?.clarification||{};
       const selection=(data.plan_evidence||data.result?.planning||data.result?.plan_evidence||{}).selection_evidence||{};
       const clarificationState=String(clarification.state||selection.clarification?.state||'').toLowerCase();
       if(status==='COMPLETED'||status==='PARTIAL') return ['complete','complete','complete','complete','complete'];
       const phaseIndex={resolve:0,clarify:1,plan:2,validate:2,execute:3,answer:4,evidence:4}[phase];
       if(phaseIndex!==undefined&&['SUBMITTED','QUEUED','RUNNING','PLANNING','EXECUTING','WAITING_FOR_DECISION'].includes(status)) {
         const states=['waiting','waiting','waiting','waiting','waiting'];
         for(let index=0;index<phaseIndex;index++) states[index]='complete';
         states[phaseIndex]=status==='WAITING_FOR_DECISION'||status==='NEEDS_CLARIFICATION'?'active':'active';
         return states;
       }
       if(status==='EXECUTING') return ['complete','complete','complete','active','waiting'];
      if(status==='QUEUED') return ['complete','complete','active','waiting','waiting'];
      if(status==='WAITING_FOR_DECISION') return ['complete','active','waiting','waiting','waiting'];
      if(status==='PLANNED') return ['complete','complete','complete','waiting','waiting'];
      if(status==='NEEDS_CLARIFICATION') return ['complete',(['required','ambiguous','unavailable','needs_facts'].includes(clarificationState)?'active':'complete'),'active','waiting','waiting'];
      if(['FAILED','REJECTED','BLOCKED','CANCELLED','TIMED_OUT'].includes(status)) return ['complete','complete','failed','unavailable','unavailable'];
      if(status==='PLANNING') return ['active','waiting','waiting','waiting','waiting'];
      return ['waiting','waiting','waiting','waiting','waiting'];
    }
    function renderAgentStageBar(data) {
      const target=$('agentStageBar');
      if(!target) return;
      const status=typeof data==='string'?data:(data?.status||'IDLE');
      const states=agentStageStates(data);
      const stateLabels={complete:'已完成',active:'进行中',waiting:'待处理',failed:'未完成',unavailable:'未执行'};
      target.dataset.status=String(status).toUpperCase();
      target.innerHTML=AGENT_STAGE_DEFINITIONS.map(([label,short],index)=>'<span class="agent-stage is-'+states[index]+'"><i aria-hidden="true"></i><b>'+short+'</b><small>'+stateLabels[states[index]]+'</small><em class="sr-only">'+label+'</em></span>').join('');
      target.setAttribute('aria-label','Agent 处理阶段：'+statusName(status));
    }
     function setStatus(value) {
      const statusValue=typeof value==='object'?(value?.status||'IDLE'):value;
      const label=statusName(statusValue);
      const normalized=String(statusValue||'').toUpperCase();
       const busy=['SUBMITTED','QUEUED','RUNNING','PLANNING','EXECUTING'].includes(normalized);
      const el=$('status');
      el.textContent=label;
      el.className='badge '+String(statusValue).toLowerCase();
      el.setAttribute('aria-label','运行状态：'+label);
      $('chatPanel')?.setAttribute('aria-busy',busy?'true':'false');
      $('resultWorkspace')?.setAttribute('aria-busy',busy?'true':'false');
       renderAgentStageBar(typeof value==='object'?value:(normalized||'IDLE'));
     }
     function liveDurationText() { const elapsed=Number.isFinite(liveRunState.runElapsedMs)?Math.max(0,liveRunState.runElapsedMs):Math.max(0,Date.now()-(liveRunState.startedAt||Date.now())); return elapsed<1000?'< 1 秒':Math.round(elapsed/1000)+' 秒'; }
     function liveHeartbeatText() { if(!liveRunState.lastEventAt) return '尚未收到事件'; const elapsed=Math.max(0,Date.now()-liveRunState.lastEventAt); return elapsed<1000?'刚刚':Math.round(elapsed/1000)+' 秒前'; }
     function liveBudgetDuration(milliseconds) { const value=Number(milliseconds); if(!Number.isFinite(value)) return ''; if(value<1000) return '< 1 秒'; return Math.round(value/1000)+' 秒'; }
     function liveBudgetText() { const state=liveRunState.budgetState; const remaining=liveBudgetDuration(liveRunState.runRemainingMs); const base=state==='exhausted'?'预算已耗尽':remaining?'剩余预算 '+remaining:state==='warning'?'预算接近上限':'预算等待事件'; const retries=liveRunState.retryCount?' · 重试 '+liveRunState.retryCount:''; const heartbeats=liveRunState.heartbeatCount?' · 心跳 '+liveRunState.heartbeatCount:''; const recovery=liveRunState.recoveryAction?' · 可'+(liveRunState.recoveryAction==='retry'?'重试':liveRunState.recoveryAction==='recover'?'恢复':'继续处理'):''; return base+retries+heartbeats+recovery; }
     function liveSummaryVisible(visible) { const target=$('liveRunSummary'); if(!target) return; target.hidden=!visible; if(!visible) target.open=false; }
     function stopLiveRun(options={}) {
       liveRunConsumer?.stop?.();
       liveRunConsumer=null;
       if(liveRunTicker!==null){ window.clearInterval(liveRunTicker); liveRunTicker=null; }
       if(liveRunDetailTimer!==null){ window.clearTimeout(liveRunDetailTimer); liveRunDetailTimer=null; }
       liveRunState.detailPolling=false;
       if(!options.preserve){ if(activeRunId&&activeRunId===liveRunState.runId){ activeRunId=null; activeRunDomainId=null; activeRunParams={}; setCancelState(false); } liveRunState.answerStream?.reset?.(); liveSummaryVisible(false); $('liveRunEvents')?.replaceChildren(); liveRunState.runId=''; liveRunState.domainId=''; liveRunState.request=''; liveRunState.startedAt=0; liveRunState.lastEventAt=0; liveRunState.lastSequence=0; liveRunState.eventCount=0; liveRunState.currentPhase=''; liveRunState.currentAction=''; liveRunState.transport=''; liveRunState.answerBuffer=''; liveRunState.answerStream=null; liveRunState.answerMessage=null; liveRunState.finalizing=false; liveRunState.runElapsedMs=null; liveRunState.phaseElapsedMs=null; liveRunState.runRemainingMs=null; liveRunState.phaseRemainingMs=null; liveRunState.budgetState=''; liveRunState.heartbeatCount=0; liveRunState.retryCount=0; liveRunState.recoveryAction=''; }
     }
     function createLiveAssistantMessage(runId) {
       const wrap=document.createElement('div');
       wrap.className='msg assistant live-answer-message';
       const role=document.createElement('div');
       role.className='role';
       role.textContent='智能体';
       const bubble=document.createElement('div');
       bubble.className='bubble live-answer-bubble';
       bubble.setAttribute('aria-label','智能体正在生成答案');
       const typing=document.createElement('span');
       typing.className='live-answer-typing';
       typing.setAttribute('aria-hidden','true');
       const typingLabel=document.createElement('span');
       typingLabel.textContent='正在生成答案';
       const dots=document.createElement('span');
       dots.className='live-answer-typing-dots';
       dots.setAttribute('aria-hidden','true');
       typing.append(typingLabel,dots);
       const accessibleStatus=document.createElement('span');
       accessibleStatus.className='sr-only';
       accessibleStatus.textContent='正在生成答案';
       bubble.append(typing,accessibleStatus);
       wrap.append(role,bubble);
       $('messages').appendChild(wrap);
       $('messages').scrollTop=$('messages').scrollHeight;
       return {runId,wrap,bubble,typing};
     }
     function renderLiveAssistantMessage(text) {
       const message=liveRunState.answerMessage;
       if(!message||message.runId!==liveRunState.runId) return;
       if(message.typing){ message.typing.remove(); message.typing=null; }
       message.bubble.removeAttribute('aria-label');
       message.bubble.textContent=String(text||'');
       message.bubble.classList.add('is-streaming');
       $('messages').scrollTop=$('messages').scrollHeight;
     }
     function completeLiveAssistantMessage(runId) {
       const message=liveRunState.answerMessage;
       if(!message||message.runId!==runId) return false;
       message.bubble.classList.remove('is-streaming');
       message.wrap.classList.add('msg-linked');
       message.wrap.dataset.runId=runId;
       message.wrap.title='打开该次运行的完整详情（不重新执行模型）';
       message.wrap.addEventListener('click',()=>openRunDetail(runId));
       return true;
     }
     function appendLiveEvent(event) {
       const list=$('liveRunEvents'); if(!list) return;
       const item=document.createElement('li');
       item.className='live-event live-event-'+String(event.kind||'state').replace(/[^a-z0-9_-]/gi,'-');
       const label=window.ConsoleRunEvents?.kindLabel?window.ConsoleRunEvents.kindLabel(event.kind):'运行状态';
       const message=event.message||label;
       item.innerHTML='<span class="live-event-dot" aria-hidden="true"></span><span class="live-event-copy"><b>'+escapeHtml(label)+'</b><span>'+escapeHtml(message)+'</span></span><small>#'+escapeHtml(event.sequence)+'</small>';
       list.prepend(item);
       while(list.children.length>8) list.lastElementChild.remove();
     }
     function refreshLiveSummary() {
       const phaseLabel=window.ConsoleRunEvents?.phaseLabel?window.ConsoleRunEvents.phaseLabel(liveRunState.currentPhase):'处理中';
       const phase=$('liveRunPhase'),duration=$('liveRunDuration'),action=$('liveRunAction'),heartbeat=$('liveRunHeartbeat'),budget=$('liveRunBudget'),meta=$('liveSummaryMeta'),subtitle=$('subtitle');
       if(phase) phase.textContent=phaseLabel;
       if(duration) duration.textContent=liveDurationText();
       const elapsed=Date.now()-(liveRunState.startedAt||Date.now());
       const planningWait=liveRunState.currentPhase==='plan'&&elapsed>=12000&&!liveRunState.finalizing;
       const actionText=liveRunState.currentAction||'运行时正在准备下一步';
       if(action) action.textContent=planningWait?actionText+' · 模型响应较慢，已等待 '+liveDurationText()+'。':actionText;
       if(planningWait&&subtitle) subtitle.textContent='模型响应较慢，仍在等待返回（已等待 '+liveDurationText()+'）。';
       if(heartbeat) heartbeat.textContent=liveHeartbeatText();
       if(budget) budget.textContent=liveBudgetText();
       if(meta) meta.textContent=(liveRunState.transport==='polling'?'轮询降级 · ':'实时事件 · ')+liveRunState.eventCount+' 个事件'+(liveBudgetDuration(liveRunState.phaseElapsedMs)?' · 本阶段 '+liveBudgetDuration(liveRunState.phaseElapsedMs):'');
       const fill=$('liveProgressFill'); if(fill){ const map={resolve:18,clarify:30,plan:48,validate:58,execute:74,answer:88,evidence:96}; fill.style.width=(map[liveRunState.currentPhase]||12)+'%'; }
     }
     function renderLiveRunShell(data,request) {
       const safe=normalizeConsoleResult(data).data;
       lastRunData=safe;
       liveSummaryVisible(true);
       if($('liveRunSummary')) $('liveRunSummary').open=false;
       $('resultEmpty').style.display='none';
       setResultPanel('.result-panel',false);
       setResultPanel('.answer-result',true);
       setAdvancedVisibility(false);
       $('title').textContent='正在分析';
       $('subtitle').textContent='Agent 正在分阶段处理请求，进展会实时更新。';
       $('answer').textContent='正在分析，请稍候…';
       $('answer').className='answer muted';
       $('answerProjection').innerHTML=''; $('answerProjection').hidden=true;
       $('error').innerHTML='';
       $('liveRunAction').textContent=request?'已接收请求，等待运行时接管':'等待运行时接管';
       setStatus({status:safe.status||'QUEUED',phase:liveRunState.currentPhase||'resolve'});
       refreshLiveSummary();
     }
     function handleLiveEvent(event) {
       if(!event||event.run_id!==liveRunState.runId||liveRunState.finalizing) return;
       liveRunState.lastSequence=event.sequence; liveRunState.lastEventAt=Date.now(); liveRunState.eventCount+=1;
       if(event.phase) liveRunState.currentPhase=event.phase;
       const timing=event.data||{};
       if(Number.isFinite(timing.run_elapsed_ms)) liveRunState.runElapsedMs=timing.run_elapsed_ms;
       if(Number.isFinite(timing.phase_elapsed_ms)) liveRunState.phaseElapsedMs=timing.phase_elapsed_ms;
       if(Number.isFinite(timing.run_budget_remaining_ms)) liveRunState.runRemainingMs=timing.run_budget_remaining_ms;
       if(Number.isFinite(timing.phase_remaining_ms)) liveRunState.phaseRemainingMs=timing.phase_remaining_ms;
       if(typeof timing.budget_state==='string') liveRunState.budgetState=timing.budget_state;
       if(Number.isFinite(timing.heartbeat_count)) liveRunState.heartbeatCount=timing.heartbeat_count;
       if(Number.isFinite(timing.retry_count)) liveRunState.retryCount=timing.retry_count;
       if(typeof timing.recovery_action==='string') liveRunState.recoveryAction=timing.recovery_action;
       const tool=event.data?.tool;
       liveRunState.currentAction=event.message||((tool?'正在处理工具：'+tool:'')||'运行时正在处理当前阶段');
       if(event.kind==='answer_delta'&&typeof event.data?.answer_delta==='string'){
         if(liveRunState.answerStream) liveRunState.answerStream.push(event.data.answer_delta);
         else {
           liveRunState.answerBuffer=(liveRunState.answerBuffer+event.data.answer_delta).slice(0,6000);
           $('answer').textContent=liveRunState.answerBuffer;
           $('answer').className='answer';
         }
       }
       if(event.status) setStatus({status:event.status,phase:event.phase||liveRunState.currentPhase});
       $('subtitle').textContent=event.message||('Agent 正在'+(window.ConsoleRunEvents?.phaseLabel?window.ConsoleRunEvents.phaseLabel(event.phase):'处理中')+'。');
       appendLiveEvent(event); refreshLiveSummary();
     }
    renderAgentStageBar('IDLE');
    function appendMessage(role, text, runId) { const labels={user:'你',assistant:'智能体',system:'系统'}; const wrap=document.createElement('div'); wrap.className='msg '+role; wrap.innerHTML='<div class="role">'+labels[role]+'</div><div class="bubble">'+escapeHtml(text)+'</div>'; if(runId){ wrap.classList.add('msg-linked'); wrap.dataset.runId=runId; wrap.title='打开该次运行的完整详情（不重新执行模型）'; wrap.addEventListener('click',()=>openRunDetail(runId)); } $('messages').appendChild(wrap); $('messages').scrollTop=$('messages').scrollHeight; }
    function selectedDomainLabel() { return $('domain').selectedOptions[0]?.textContent||'默认领域'; }
    function welcome() { appendMessage('assistant','当前领域：'+selectedDomainLabel()+'。你可以直接提出开放式问题；能力、工具与展示方式由该 Domain Pack 动态提供。'); }
    function resetConversationView(reason='reset') { $('messages').innerHTML=''; $('answer').textContent=''; $('answer').className='answer muted'; $('error').innerHTML=''; $('goal').textContent=''; $('decisionMode').textContent='等待决策'; $('steps').innerHTML=''; $('provenance').innerHTML=''; $('trace').innerHTML=''; $('links').innerHTML=''; renderAgentStageBar('IDLE'); resetResultWorkspace(reason); }
    function selectedConversationLabel() { return $('session').selectedOptions[0]?.textContent || '对话1'; }
    function addConversationOption(session,domainId=currentDomainId()) { if(!session?.session_id) return; sessionDomains.set(String(session.session_id),domainId); let option=[...$('session').options].find(item=>item.value===session.session_id); if(!option){ option=document.createElement('option'); option.value=session.session_id; $('session').appendChild(option); } option.dataset.domainId=domainId; option.textContent=session.display_name||'对话'+($('session').options.length); }
    async function loadSessions(domainId=currentDomainId()) {
      const catalogGeneration=sessionCatalogGeneration;
      $('session').innerHTML='';
      try {
        const response=await nativeFetch(domainPath('/sessions?limit=50',domainId));
        const data=await response.json().catch(()=>({}));
        if(!response.ok) throw new Error(responseError(data,'会话目录不可用'));
        if(domainId!==currentDomainId()||catalogGeneration!==sessionCatalogGeneration) return;
        (data.sessions||[]).forEach(session=>addConversationOption(session,domainId));
      } catch(error) {
        if(domainId!==currentDomainId()||catalogGeneration!==sessionCatalogGeneration) return;
        appendMessage('system','当前领域的会话目录暂不可用，将使用本地临时会话。');
      }
      if(domainId!==currentDomainId()||catalogGeneration!==sessionCatalogGeneration) return;
      if(!$('session').options.length) await newSession(domainId,false);
      if(domainId!==currentDomainId()||catalogGeneration!==sessionCatalogGeneration) return;
      $('chatMeta').textContent='当前对话：'+selectedConversationLabel();
    }
    async function loadDomains() {
      try {
        const response=await nativeFetch('/domains');
        const data=await response.json().catch(()=>({}));
        if(!response.ok) throw new Error(responseError(data,'领域目录不可用'));
        const domains=Array.isArray(data.domains)?data.domains.filter(item=>item&&item.id):[];
        if(!domains.length) throw new Error('领域目录为空');
        domainCatalog=data;
        legacyRouting=false;
        $('domain').innerHTML='<option value="'+AUTO_DOMAIN_VALUE+'" title="由运行时根据请求和当前会话选择领域">智能选择</option>'+domains.map(item=>'<option value="'+escapeHtml(item.id)+'" title="'+escapeHtml(item.description||'')+'">'+escapeHtml(item.label||item.id)+'</option>').join('');
        const preferred=preferredDomainId();
        const available=new Set([AUTO_DOMAIN_VALUE,...domains.map(item=>String(item.id))]);
        const defaultDomain=available.has('gis')?'gis':(available.has(data.legacy_domain_id)?data.legacy_domain_id:String(domains[0].id));
        $('domain').value=available.has(preferred)?preferred:defaultDomain;
        if($('domain').value===AUTO_DOMAIN_VALUE) autoDomainBinding=preferredAutoDomainBinding(available);
        persistSelectedDomain();
        return data;
      } catch(error) {
        legacyRouting=true;
        domainCatalog={domains:[],legacy:true};
        $('domain').innerHTML='<option value="'+LEGACY_DOMAIN_VALUE+'">默认领域（兼容模式）</option>';
        $('domain').value=LEGACY_DOMAIN_VALUE;
        $('capabilityStatus').textContent='动态领域目录加载失败，已降级到旧版默认领域；部分多领域功能不可用。';
        return domainCatalog;
      }
    }
    async function reloadDomainContext() {
      const domainId=currentDomainId();
      const generation=++domainGeneration;
      sessionCatalogGeneration++;
      conversationGeneration++;
      window.__consoleDomainReady=false;
      $('send').disabled=true;
      $('previewPlan').disabled=true;
      persistSelectedDomain();
      workflowTemplates={};
      actionCatalog={schema_version:'spatial-agent.actions.v1',domain_id:domainId,actions:[]};
      actionCatalogPromise=null;
      runtimeEvidenceSnapshot=null;
      runtimeEvidencePromise=null;
      lastPlanPreview=null;
      $('toolGovernanceMeta').textContent='正在读取审批状态…';
      $('toolApprovals').innerHTML='<div class="tool-governance-empty">正在读取工具审批状态…</div>';
      resetConversationView();
      welcome();
      $('session').innerHTML='';
      if(usesAutoRouting()&&!autoDomainBinding) {
        $('workflow').innerHTML='<option value="">智能选择（默认）</option>';
        renderWorkflowEditor();
        $('chatMeta').textContent='首次请求将创建领域绑定会话';
        $('capabilityStatus').textContent='智能选择将在提交请求后匹配已注册领域；当前尚未访问任何领域状态。';
        $('historyList').innerHTML='<div class="muted">领域选定后显示该领域的历史任务。</div>';
        $('runtimeMetrics').textContent='领域选定后显示运行指标。';
        $('actionWorkbenchBody').innerHTML='<div class="distribution-note">领域选定后加载可执行动作。</div>';
        $('newSession').disabled=false;
        $('clearAllSessions').disabled=false;
        $('deleteSession').disabled=true;
        $('previewPlan').disabled=true;
        window.__consoleDomainReady=true;
        $('send').disabled=false;
        return;
      }
      $('newSession').disabled=false;
      $('deleteSession').disabled=false;
      $('historyList').innerHTML='<div class="muted">正在读取当前领域历史任务…</div>';
      $('runtimeMetrics').textContent='正在读取当前领域运行指标…';
      await Promise.all([loadCapabilities(domainId),loadActions(domainId),loadWorkflows(domainId),loadSessions(domainId),loadToolApprovals(domainId)]);
      if(generation!==domainGeneration||domainId!==currentDomainId()) return;
      if(generation===domainGeneration&&domainId===currentDomainId()) { window.__consoleDomainReady=true; $('send').disabled=false; $('previewPlan').disabled=false; }
      Promise.allSettled([loadHistory(domainId),restoreSession(domainId)]).catch(()=>{});
    }
    async function hydrateAutoDomainState(data) {
      if(!usesAutoRouting()) return;
      const domainId=bindAutoDomain(data);
      if(!domainId) return;
      const generation=domainGeneration;
      const sessionId=data?.session_id||autoDomainBinding?.session_id||'';
      $('newSession').disabled=false;
      $('deleteSession').disabled=false;
      $('previewPlan').disabled=false;
      await Promise.all([loadCapabilities(domainId),loadActions(domainId),loadWorkflows(domainId),loadSessions(domainId),loadToolApprovals(domainId)]);
      if(generation!==domainGeneration||!usesAutoRouting()||currentDomainId()!==domainId) return;
      if(sessionId){
        const option=[...$('session').options].find(item=>item.value===sessionId);
        if(!option) addConversationOption({session_id:sessionId,display_name:'对话'+($('session').options.length+1)},domainId);
        $('session').value=sessionId;
        $('chatMeta').textContent='当前对话：'+selectedConversationLabel()+' · 已绑定 '+selectedDomainContextLabel(domainId);
      }
      window.__consoleDomainReady=true;
      $('send').disabled=false;
      loadHistory(domainId).catch(()=>{});
    }
    function selectedDomainContextLabel(domainId) { const item=(domainCatalog.domains||[]).find(domain=>String(domain.id)===String(domainId)); return item?.label||domainId; }
    function workflowFieldId(name) { return 'workflow-field-'+String(name).replace(/[^A-Za-z0-9_-]/g,'-'); }
    function renderWorkflowEditor() {
      const template=workflowTemplates[$('workflow').value];
      $('workflowFields').innerHTML=''; $('workflowEvidence').innerHTML=''; $('workflowValidation').textContent=''; $('workflowValidation').className='workflow-validation';
      if(!template){ $('workflowFields').innerHTML='<div class="distribution-note">由 Agent 根据问题自动选择工作流。</div>'; return; }
      $('workflowFields').innerHTML=(template.constraint_specs||[]).map(spec=>{
        const id=workflowFieldId(spec.name), required=spec.required?' required':'';
        const label=escapeHtml(spec.label||spec.name)+(spec.required?' · 必填':'');
        if(spec.type==='boolean') return '<label class="workflow-boolean" for="'+id+'"><input id="'+id+'" data-workflow-field="'+escapeHtml(spec.name)+'" data-type="boolean" type="checkbox"'+(spec.default?' checked':'')+'>'+label+'</label>';
        if(spec.type==='enum') return '<div class="workflow-field"><label for="'+id+'">'+label+'</label><select id="'+id+'" data-workflow-field="'+escapeHtml(spec.name)+'" data-type="enum"'+required+'><option value="">请选择</option>'+(spec.choices||[]).map(choice=>'<option value="'+escapeHtml(choice)+'">'+escapeHtml(choice)+'</option>').join('')+'</select></div>';
        const attrs=(spec.min!==undefined?' min="'+escapeHtml(spec.min)+'"':'')+(spec.max!==undefined?' max="'+escapeHtml(spec.max)+'"':'')+(spec.type==='number'?' step="any"':'');
        return '<div class="workflow-field"><label for="'+id+'">'+label+'</label><input id="'+id+'" data-workflow-field="'+escapeHtml(spec.name)+'" data-type="'+escapeHtml(spec.type)+'" type="'+(spec.type==='string'?'text':'number')+'"'+attrs+required+(spec.default!==undefined?' value="'+escapeHtml(spec.default)+'"':'')+'></div>';
      }).join('');
      $('workflowEvidence').innerHTML='<div class="distribution-note">结果证据</div>'+(template.evidence_options||[]).map(option=>'<label><input type="checkbox" data-workflow-evidence="'+escapeHtml(option)+'"'+((template.default_evidence||[]).includes(option)?' checked':'')+'>'+escapeHtml(option)+'</label>').join('');
    }
    function collectWorkflowSelection() {
      const templateId=$('workflow').value;
      if(!templateId) return null;
      const constraints={};
      document.querySelectorAll('[data-workflow-field]').forEach(field=>{
        if(field.dataset.type==='boolean') constraints[field.dataset.workflowField]=field.checked;
        else if(field.value!=='') constraints[field.dataset.workflowField]=field.dataset.type==='number'?Number(field.value):field.value;
      });
      return {template_id:templateId,constraints,evidence:[...document.querySelectorAll('[data-workflow-evidence]:checked')].map(field=>field.dataset.workflowEvidence)};
    }
    async function validateWorkflowSelection() {
      const selection=collectWorkflowSelection();
      if(!selection) return null;
      const domainId=currentDomainId();
      const body=withDomainPayload(Object.assign({},selection,{planner:$('planner').value,backend:$('backend').value}),domainId);
      const response=await nativeFetch(domainPath('/workflows/'+encodeURIComponent(selection.template_id)+'/validate',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await response.json();
      if(!response.ok) { const message=responseError(data,'工作流参数校验失败'); $('workflowValidation').textContent=message; $('workflowValidation').className='workflow-validation error'; throw new Error(message); }
      selection.constraints=data.constraints; selection.evidence=data.evidence; $('workflowValidation').textContent='已通过 '+escapeHtml(data.template.label)+' 契约校验 · v'+escapeHtml(data.template.version); return selection;
    }
    async function loadWorkflows(domainId=currentDomainId()) { try { const response=await nativeFetch(domainPath('/workflows',domainId)); if(!response.ok) throw new Error('workflow catalog unavailable'); const data=await response.json(); if(domainId!==currentDomainId()) return; workflowTemplates=data.templates||{}; $('workflow').innerHTML='<option value="">智能选择（默认）</option>'+Object.values(workflowTemplates).map(template=>'<option value="'+escapeHtml(template.id)+'">'+escapeHtml(template.label)+' · v'+escapeHtml(template.version)+'</option>').join(''); renderWorkflowEditor(); } catch(error) { if(domainId===currentDomainId()) $('workflowValidation').textContent='工作流目录暂不可用，继续使用智能选择。'; } }
    function nextConversationName() { return '对话'+String($('session').options.length+1); }
    function localSession(domainId) {
      const identity=globalThis.crypto?.randomUUID?.()||String(Date.now())+'-'+Math.random().toString(16).slice(2);
      const prefix=domainId===AUTO_DOMAIN_VALUE?'conversation-auto-draft-':'conversation-local-';
      const session={session_id:prefix+String(identity).replace(/[^A-Za-z0-9_-]/g,'').slice(0,64),display_name:nextConversationName()};
      localDraftSessionIds.add(session.session_id);
      return session;
    }
    async function newSession(domainId=currentDomainId(),reset=true) {
      if(domainId!==currentDomainId()) return null;
      let session;
      if(usesAutoRouting()&&!autoDomainBinding&&domainId===AUTO_DOMAIN_VALUE) {
        session=localSession(domainId);
        autoDraftSessionId=session.session_id;
      } else {
        try {
          const response=await nativeFetch(domainPath('/sessions',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
          const data=await response.json().catch(()=>({}));
          if(!response.ok) throw new Error(responseError(data,'创建会话失败（HTTP '+response.status+'）'));
          if(!data?.session_id) throw new Error('创建会话失败：服务未返回会话标识');
          session=Object.assign({display_name:nextConversationName()},data);
        } catch(error) {
          if(domainId!==currentDomainId()) return null;
          if(!usesLegacyRouting(domainId)) {
            $('error').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>';
            return null;
          }
          session=localSession(domainId);
        }
      }
      if(domainId!==currentDomainId()) return null;
      addConversationOption(session,domainId);
      $('session').value=session.session_id;
      $('deleteSession').disabled=false;
      if(usesAutoRouting()&&domainId!==AUTO_DOMAIN_VALUE) {
        autoDomainBinding={domain_id:String(domainId),session_id:String(session.session_id)};
        autoDraftSessionId='';
        persistAutoDomainBinding();
      }
      $('chatMeta').textContent='当前对话：'+selectedConversationLabel();
      if(reset){ conversationGeneration++; resetConversationView(); welcome(); }
      $('prompt').focus();
      return session;
    }
    async function clearChat() {
      conversationGeneration++;
      const sessionId=$('session').value;
      if(usesAutoRouting()&&!autoDomainBinding){
        const draftSessionId=autoDraftSessionId||sessionId;
        resetConversationView('clear-session'); welcome(); $('prompt').focus();
        domainRoutingRequests.clear(); autoDraftSessionId='';
        if(draftSessionId) localDraftSessionIds.delete(draftSessionId);
        if(draftSessionId) nativeFetch('/domain-routing/sessions/'+encodeURIComponent(draftSessionId)+'/clear',{method:'POST'}).catch(()=>{});
        return;
      }
      const domainId=sessionDomains.get(sessionId)||currentDomainId();
      resetConversationView('clear-session');
      welcome();
      $('prompt').focus();
      try {
        const response=await nativeFetch(domainPath('/sessions/'+encodeURIComponent(sessionId)+'/clear',domainId),{method:'POST'});
        if(!response.ok) throw new Error('对话历史清理失败（HTTP '+response.status+'）');
        if(domainId===currentDomainId()) await loadHistory(domainId);
      } catch(error) {
        $('error').innerHTML='<div class="error">界面已清空，但对话持久化清理失败：'+escapeHtml(error.message)+'</div>';
      }
    }
    async function deleteConversation() {
      const sessionId=$('session').value;
      if(!sessionId || !window.confirm('删除当前对话及其历史任务？')) return;
      conversationGeneration++;
      if(usesAutoRouting()&&!autoDomainBinding&&localDraftSessionIds.has(sessionId)) {
        localDraftSessionIds.delete(sessionId);
        autoDraftSessionId=autoDraftSessionId===sessionId?'':autoDraftSessionId;
        const option=$('session').selectedOptions[0];
        option?.remove();
        sessionDomains.delete(sessionId);
      } else {
        const domainId=sessionDomains.get(sessionId)||currentDomainId();
        try {
          const response=await nativeFetch(domainPath('/sessions/'+encodeURIComponent(sessionId),domainId),{method:'DELETE'});
          if(!response.ok) throw new Error('删除对话失败（HTTP '+response.status+'）');
          const option=$('session').selectedOptions[0];
          option?.remove();
          sessionDomains.delete(sessionId);
        } catch(error) { $('error').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>'; return; }
      }
      let option=$('session').options[0];
      if(usesAutoRouting()) {
        if(!option){ autoDomainBinding=null; autoDraftSessionId=''; persistAutoDomainBinding(); await reloadDomainContext(); return; }
        $('session').value=option.value;
        if(autoDomainBinding) {
          autoDomainBinding={domain_id:sessionDomains.get(option.value)||autoDomainBinding.domain_id,session_id:option.value};
          persistAutoDomainBinding();
          await restoreSession(autoDomainBinding.domain_id);
        } else {
          autoDraftSessionId=option.value;
          resetConversationView();
          welcome();
        }
        return;
      }
      if(!option){ await newSession(currentDomainId()); return; }
      $('session').value=option.value;
      await restoreSession(currentDomainId());
    }
    function clearAllDomainIds(options={}) {
      if(Array.isArray(options.domainIds)) return [...new Set(options.domainIds.map(String).filter(id=>id&&id!==AUTO_DOMAIN_VALUE))];
      if(!usesAutoRouting()) return currentDomainId()===AUTO_DOMAIN_VALUE?[]:[currentDomainId()];
      const ids=(domainCatalog.domains||[]).map(item=>String(item.id)).filter(Boolean);
      if(autoDomainBinding?.domain_id) ids.push(String(autoDomainBinding.domain_id));
      return [...new Set(ids)];
    }
    async function clearAllSessions(options={}) {
      if(options.confirm!==false&&!window.confirm('清空全部对话及其历史任务？此操作不可撤销。')) return {cancelled:true};
      const button=$('clearAllSessions');
      if(button) button.disabled=true;
      conversationGeneration++;
      sessionCatalogGeneration++;
      const failures=[];
      let deleted=0;
      const domains=clearAllDomainIds(options);
      const targets=[];
      if(options.includePersisted!==false) {
        for(const domainId of domains) {
          try {
            const listResponse=await nativeFetch(domainPath('/sessions?limit=200',domainId));
            const listData=await listResponse.json().catch(()=>({}));
            if(!listResponse.ok) throw new Error(responseError(listData,'读取会话目录失败（HTTP '+listResponse.status+'）'));
            (listData.sessions||[]).forEach(session=>{ const sessionId=String(session?.session_id||''); if(sessionId) targets.push({domainId,sessionId}); });
          } catch(error) { failures.push((selectedDomainContextLabel(domainId)||domainId)+'：'+error.message); }
        }
      }
      const routingTargets=options.includeRouting===false?[]:[...localDraftSessionIds];
      sessionDomains.clear();
      runDomains.clear();
      actionDomains.clear();
      decisionDomains.clear();
      domainRoutingRequests.clear();
      localDraftSessionIds.clear();
      autoDraftSessionId='';
      autoDomainBinding=null;
      persistAutoDomainBinding();
      $('session').innerHTML='';
      resetConversationView();
      if(usesAutoRouting()) await newSession(AUTO_DOMAIN_VALUE,false);
      else await newSession(currentDomainId(),false);
      $('chatMeta').textContent='当前对话：'+selectedConversationLabel();
      $('subtitle').textContent='正在清理旧对话，当前空白会话已可继续使用。';
      welcome();
      $('prompt').focus();
      try {
        for(const target of targets) {
          try {
            const response=await nativeFetch(domainPath('/sessions/'+encodeURIComponent(target.sessionId),target.domainId),{method:'DELETE'});
            const data=await response.json().catch(()=>({}));
            if(!response.ok) throw new Error(responseError(data,'删除会话失败（HTTP '+response.status+'）'));
            deleted++;
          } catch(error) { failures.push((selectedDomainContextLabel(target.domainId)||target.domainId)+' / '+target.sessionId+'：'+error.message); }
        }
        for(const sessionId of routingTargets) {
          try {
            const response=await nativeFetch('/domain-routing/sessions/'+encodeURIComponent(sessionId)+'/clear',{method:'POST'});
            if(!response.ok) throw new Error('清理路由草稿失败（HTTP '+response.status+'）');
          } catch(error) { failures.push('路由草稿 '+sessionId+'：'+error.message); }
        }
      } finally {
        if(button) button.disabled=false;
      }
      const result={deleted,failures,remaining:$('session').options.length};
      if(failures.length) {
        $('subtitle').textContent='部分旧对话清理失败，但当前空白会话仍可继续使用。';
        $('error').innerHTML='<div class="error">已清理 '+deleted+' 个对话，但有 '+failures.length+' 项未完成：'+escapeHtml(failures.join('；'))+'</div>';
      } else {
        $('subtitle').textContent='旧对话已清理，可以继续提出新的问题。';
        appendMessage('system','已清空全部对话，已为你准备一个新的空白对话。');
      }
      return result;
    }
    function metrics(data) { const m=data.planner_metrics||{}; const items=[['模型',m.model||'-'],['接口协议',m.wire_api||'-'],['规划耗时',m.latency_ms ? m.latency_ms+' 毫秒':'-']]; const usage=m.usage||{}; if(usage.total_tokens!==undefined) items.push(['令牌用量',usage.total_tokens]); $('metrics').innerHTML=items.map(x=>'<div class="metric"><b>'+escapeHtml(x[1])+'</b><small>'+escapeHtml(x[0])+'</small></div>').join(''); }
    function stepResult(result) { if(!result) return '未返回工具结果'; if(result.error) return '业务错误：'+result.error; const summary=result.summary||result.answer||result.message; if(typeof summary==='string'&&summary.trim()) return summary.trim(); const values=Object.entries(result).filter(([key,value])=>!['schema_version','status','result_ref','artifact_ref'].includes(key)&&['string','number','boolean'].includes(typeof value)).slice(0,4); return values.length?values.map(([key,value])=>key+'：'+value).join(' · '):'已返回结构化结果'; }
    function conversationTurnLabel(data) { const turn=data.conversation_turn||data.result?.conversation_turn; if(!turn||turn.available===false) return ''; const labels={new_request:'新请求',clarification_reply:'澄清回复',follow_up:'后续追问',decision_reply:'决策回复',unknown:'未知轮次'}; const mode=labels[turn.mode]||'未知轮次'; const relation=turn.pending_consumed?' · 已消费待澄清请求':turn.pending_available?' · 未消费旧待澄清请求':''; return '本轮：'+mode+relation; }
    function decisionMode(data) { const type=data.result?.type || data.result_type || data.plan?.output?.type; const turn=conversationTurnLabel(data); const suffix=turn?turn+' · ':''; if(type==='direct_answer') return suffix+'通用回答 · 未调用工具'; if(data.status==='WAITING_FOR_DECISION') return suffix+'计划已生成 · 等待用户确认'; if(data.status==='NEEDS_CLARIFICATION') return suffix+'需要补充信息 · 暂未调用工具'; if(data.status==='REJECTED') return suffix+'请求已拒绝 · 未执行工具'; const count=(data.steps||[]).length; if(count) return suffix+'工具计划 · 已执行 '+count+' 个步骤'; return suffix+'等待决策'; }
    function renderClarification(data) { const details=data.clarification||data.result?.clarification; if(data.status!=='NEEDS_CLARIFICATION'||!details) return; const catalogLabels=Object.fromEntries((details.suggested_capability_details||[]).map(item=>[item.id,item.label])); const capabilities=(details.matched_capabilities||[]).concat(details.matched_capabilities?.length?[]:(details.suggested_capabilities||[]).slice(0,5)); const capabilityText=capabilities.map(item=>catalogLabels[item]||item); const missing=(details.missing||[]).join('、'); const actions=(details.next_actions||[]).map(item=>'<li>'+escapeHtml(item)+'</li>').join(''); const heading=missing?'已匹配能力，但参数还不完整':'需要选择或补充能力信息'; const html='<div class="clarification-box"><strong>'+escapeHtml(heading)+'</strong>'+(missing?'<span>待补充：'+escapeHtml(missing)+'</span>':'')+(capabilityText.length?'<small>相关能力：'+escapeHtml(capabilityText.join('、'))+'</small>':'')+(actions?'<ul>'+actions+'</ul>':'')+'</div>'; $('answer').innerHTML=html; $('answer').className='answer'; }
    function steps(data) { const list=data.steps||[]; $('steps').innerHTML=list.length?list.map(s=>'<li><div class="step-head"><span class="step-tool">'+escapeHtml(s.tool)+'</span><span class="step-status '+String(s.status||'').toLowerCase()+'">'+escapeHtml(statusName(s.status))+'</span></div><div class="muted">'+escapeHtml(s.latency_ms||'-')+' 毫秒 · '+escapeHtml(s.attempts||0)+' 次尝试</div>'+(s.depends_on&&s.depends_on.length?'<div class="step-deps">依赖：'+escapeHtml(s.depends_on.join('、'))+'</div>':'<div class="step-deps">无前置依赖</div>')+'<div class="step-result">'+escapeHtml(stepResult(s.result)||((s.error)?'执行错误：'+s.error:'未返回工具结果'))+'</div></li>').join(''):'<li class="muted">暂无工具步骤。</li>'; }
    function trace(data) { $('trace').innerHTML=(data.trace_summary||[]).map(x=>'<li>'+escapeHtml(x)+'</li>').join('')||'<li class="muted">暂无执行轨迹。</li>'; }
    function provenance(data) { const p=data.provenance||{}; const list=p.steps||[]; if(!list.length){ $('provenance').innerHTML='<div class="muted">暂无运行血缘。</div>'; return; } $('provenance').innerHTML='<div class="muted">执行策略：'+escapeHtml(p.execution_policy||'未知')+'</div>'+list.map(x=>{ const deps=(x.depends_on||[]).join('、')||'无'; const bindings=(x.input_bindings||[]).map(b=>b.source_step+'.'+b.path).join('、')||'无'; const ref=x.result_ref||'无'; return '<div class="provenance-item"><b>'+escapeHtml(x.id)+' · '+escapeHtml(x.tool)+'</b><br>依赖：'+escapeHtml(deps)+'<br>输入绑定：'+escapeHtml(bindings)+'<br>结果引用：'+escapeHtml(ref)+'</div>'; }).join(''); }
    function llmHealthLabel(caps) { if(caps.live_llm) return ['真实大模型','可用',true]; if(caps.live_llm_configured) return ['真实大模型','网络受限',false]; return ['真实大模型','未配置',false]; }
    function geometryEvidence(data) { const geometry=(data.result||{}).geometry||{}; const labels={real_geometry:'真实空间要素可绘制',boundary_geometry:'行政区边界可绘制',no_geometry:'无可绘制几何（仅结果摘要）',truncated_geometry:'几何摘要已截断，不保证可完整绘制',unknown:'尚未形成空间几何证据'}; $('geometryEvidence').textContent='空间证据：'+(labels[geometry.status]||labels.unknown)+(geometry.feature_count?' · '+geometry.feature_count+' 个要素':'')+(geometry.reason?'；'+geometry.reason:''); }
    const evidenceStatusNames={ready:'可用',recoverable:'可恢复',blocked:'已阻断',degraded:'部分可用',unavailable:'不可用',passed:'通过',warning:'警告',none:'无降级',real_geometry:'真实几何',boundary_geometry:'边界几何',no_geometry:'无几何',truncated_geometry:'已截断',unknown:'未知'};
    const evidenceStatusClass=status=>({passed:'ready',warning:'degraded',none:'ready',real_geometry:'real_geometry',boundary_geometry:'boundary_geometry',no_geometry:'no_geometry',truncated_geometry:'truncated_geometry',ready:'ready',recoverable:'degraded',blocked:'unavailable',degraded:'degraded',unavailable:'unavailable',unknown:'unknown'}[String(status||'unknown')]||'unknown');
    const evidenceStatusLabel=status=>evidenceStatusNames[String(status||'unknown')]||String(status||'未知');
    const evidenceBadge=status=>'<span class="evidence-status '+evidenceStatusClass(status)+'">'+escapeHtml(evidenceStatusLabel(status))+'</span>';
    const evidenceText=value=>Array.isArray(value)?value.join('、'):value===null||value===undefined||value===''?'-':typeof value==='object'?JSON.stringify(value):String(value);
    function evidenceDataEntries(data, snapshot) { const envelope=data.result||{}; const explicit=data.data_evidence||envelope.data_evidence||snapshot.data_evidence; if(explicit&&typeof explicit==='object'&&!Array.isArray(explicit)) return Object.entries(explicit); const healthResult=((data.steps||[]).find(step=>step.tool==='get_dataset_health_report')||{}).result||{}; return (healthResult.datasets||[]).filter(item=>item&&item.dataset).map(item=>[item.dataset,item]); }
    const verificationModeLabel=mode=>({metadata:'metadata 元数据',sha256:'SHA-256 完整核验'}[String(mode||'')]||String(mode||'未知核验方式'));
    function analysisReadyBindingText(ready) { const binding=ready?.source_binding; const output=ready?.output_manifest; let text=''; if(binding&&binding.fingerprint) text+=' · 源绑定 '+(binding.status==='recorded'?'已记录':evidenceStatusLabel(binding.status))+' · '+binding.fingerprint; if(output&&output.status) text+=' · 输出 manifest '+evidenceStatusLabel(output.status)+' · '+verificationModeLabel(output.verification_mode)+(output.hashes_verified?' · SHA-256 已核验':''); return text; }
    function analysisReadyText(item) { const ready=item?.analysis_ready; if(!ready||ready.status==='not_configured') return ''; const grid=ready.target_grid||{}; const resolution=Array.isArray(grid.resolution)?grid.resolution.join('×')+' 米':'未知分辨率'; return ' · 分析就绪 '+evidenceStatusLabel(ready.status)+' · '+(ready.derived_version||'未知版本')+' · '+(grid.crs||'未知 CRS')+' · '+resolution+analysisReadyBindingText(ready); }
    function runtimeDataEvidence(data, snapshot) { const envelope=data.result||{}; return data.runtime_evidence||envelope.runtime_evidence||snapshot||{}; }
    function evidenceRevalidationText(data) { const envelope=data.result||{}; const planning=envelope.planning||data.plan_evidence||{}; const gate=planning.evidence_revalidation||data.evidence_revalidation||{}; const binding=planning.evidence_binding||data.evidence_binding||{}; if(!gate.schema_version&&!binding.schema_version) return ''; const labels={current:'当前有效',changed:'预览已失效，需重新核验',degraded:'证据降级',blocked:'证据阻断',unavailable:'证据不可用'}; const state=gate.state|| (binding.available===false?'unavailable':'current'); const fingerprint=gate.current_fingerprint||binding.fingerprint||''; const expected=gate.expected_fingerprint&&gate.expected_fingerprint!==fingerprint?' · 预览指纹 '+String(gate.expected_fingerprint).slice(0,19):''; const actions=Array.isArray(gate.next_actions)&&gate.next_actions.length?' · 下一步 '+gate.next_actions.join('、'):''; return '证据重验：'+(labels[state]||state)+ (fingerprint?' · 当前指纹 '+String(fingerprint).slice(0,19):'')+expected+actions; }
    function renderEvidence(data) {
      const envelope=data.result||{};
      const domainId=responseDomain(data);
      const geometry=envelope.geometry||data.geometry_evidence||{};
      const lineage=envelope.lineage||{};
      const contextEvidence=envelope.context||data.context_evidence||{};
      const planEvidence=envelope.planning||data.plan_evidence||{};
      const evidenceRecovery=envelope.evidence_recovery||data.evidence_recovery||{};
      const geometryStatus=geometry.status||'unknown';
      const geometryReference=geometry.reference||envelope.artifacts?.geometry||{};
      const geometryRef=geometryReference.ref||geometry.geojson_ref||data.geojson_ref;
      const geometryPath=geometryArtifactPath(geometryReference,geometryRef,domainId);
      const p=data.provenance||{};
      const provenanceSteps=Array.isArray(p.steps)?p.steps:[];
      const snapshot=runtimeDataEvidence(data,runtimeEvidenceSnapshot||{});
      const healthResult=((data.steps||[]).find(step=>step.tool==='get_dataset_health_report')||{}).result||{};
      const dataEntries=evidenceDataEntries(data,snapshot);
      const runtimeStatus=healthResult.status||snapshot.health_status||snapshot.status||'unknown';
      const runtime=snapshot.runtime||{};
      const runtimeDetails=[];
      Object.entries(runtime).filter(([,value])=>typeof value==='boolean').slice(0,8).forEach(([id,available])=>runtimeDetails.push(capabilityHealthLabel(id)+'：'+(available?'可用':'不可用')));
      const analysisReady=healthResult.analysis_ready||data.analysis_ready||snapshot.analysis_ready||{};
      if(analysisReady.status&&analysisReady.status!=='not_configured') runtimeDetails.push('分析就绪派生层：'+evidenceStatusLabel(analysisReady.status)+' · '+(analysisReady.derived_version||'未知版本')+' · '+((analysisReady.target_grid||{}).crs||'未知 CRS')+analysisReadyBindingText(analysisReady));
      if(snapshot.updated_at) runtimeDetails.push('检查时间：'+snapshot.updated_at);
      if(contextEvidence.available) runtimeDetails.push('上下文工程：'+escapeHtml(contextEvidence.schema_version||'已构建')+' · '+escapeHtml(contextEvidence.input_chars||0)+' 字符'+(contextEvidence.truncated?' · 已按预算裁剪':' · 未裁剪'));
      if(planEvidence.available) runtimeDetails.push('计划来源：'+escapeHtml(planEvidence.source||'未知')+' · '+escapeHtml(planEvidence.planner_kind||'未知规划器')+' · '+escapeHtml(planEvidence.step_count||0)+' 步'+((planEvidence.exact_template_ids||[]).length?' · 模板 '+escapeHtml((planEvidence.exact_template_ids||[]).join('、')):''));
      const planQuality=planEvidence.plan_quality||{};
      if(planQuality.schema_version) runtimeDetails.push('计划质量：'+escapeHtml(planQuality.state||'未知')+' · '+escapeHtml(planQuality.reason_code||'未提供')+(planQuality.template_id?' · '+escapeHtml(planQuality.template_id):'')+(planQuality.available===false?' · 未套用唯一模板蓝图':''));
      const planPolicy=planEvidence.plan_policy||{};
      if(planPolicy.schema_version) runtimeDetails.push('计划策略：'+escapeHtml(planPolicy.state||'未知')+' · '+(planPolicy.accepted?'已接受':'未接受')+' · '+escapeHtml(planPolicy.reason_code||'未提供')+(planPolicy.policy_id?' · '+escapeHtml(planPolicy.policy_id):'')+(planPolicy.source?' · '+escapeHtml(planPolicy.source):'')+(planPolicy.max_steps?' · 上限 '+escapeHtml(planPolicy.max_steps)+' 步':''));
      const workflowSelection=planEvidence.workflow_selection||{};
      if(workflowSelection.schema_version) runtimeDetails.push('工作流选择：'+escapeHtml(workflowSelection.state||'未知')+' · '+escapeHtml(workflowSelection.reason_code||'未提供')+(workflowSelection.selected_capability_id?' · 能力 '+escapeHtml(workflowSelection.selected_capability_id):'')+((workflowSelection.candidate_ids||[]).length?' · 候选 '+escapeHtml((workflowSelection.candidate_ids||[]).join('、')):''));
      const executionTimeline=envelope.execution_timeline||{};
      if(executionTimeline.schema_version) { const timelineEvents=Array.isArray(executionTimeline.events)?executionTimeline.events:[]; const lifecycleEvent=timelineEvents.slice().reverse().find(item=>item&&item.kind==='lifecycle')||{}; const allowedActions=Array.isArray(lifecycleEvent.allowed_actions)?lifecycleEvent.allowed_actions:[]; runtimeDetails.push('执行时间线：'+escapeHtml(executionTimeline.event_count||0)+' 个事件'+(executionTimeline.available?' · 可追溯':' · 不可用')+(allowedActions.length?' · 可执行：'+escapeHtml(allowedActions.join('、')):'')); }
      const evidenceRegistry=envelope.evidence_registry||{};
      if(evidenceRegistry.schema_version) runtimeDetails.push('证据索引：'+escapeHtml(evidenceRegistry.entry_count||0)+' 个版本化证据入口'+(evidenceRegistry.available?' · 可用':' · 不可用'));
      if(evidenceRecovery.schema_version) runtimeDetails.push('证据恢复：'+escapeHtml(evidenceRecovery.state||'未知')+' · '+escapeHtml(evidenceRecovery.reason_code||'未提供')+((evidenceRecovery.allowed_actions||[]).length?' · 可执行：'+escapeHtml(evidenceRecovery.allowed_actions.join('、')):''));
      if(planEvidence.planner_selection?.schema_version) runtimeDetails.push('规划器选择：'+escapeHtml(planEvidence.planner_selection.state||'未知')+' · '+escapeHtml(planEvidence.planner_selection.reason_code||'未提供')+(planEvidence.planner_selection.planner_capability_id?' · 能力 '+escapeHtml(planEvidence.planner_selection.planner_capability_id):'')+(planEvidence.planner_selection.result_type?' · '+escapeHtml(planEvidence.planner_selection.result_type):''));
      if(planEvidence.capability_discovery_available) runtimeDetails.push('能力发现：'+escapeHtml(planEvidence.selected_capability_id||'未选定')+((planEvidence.capability_candidate_ids||[]).length?' · 候选 '+escapeHtml((planEvidence.capability_candidate_ids||[]).join('、')):''));
      if(planEvidence.capability_catalog_available) runtimeDetails.push('能力目录：'+escapeHtml(planEvidence.capability_catalog_environment||'未知后端')+((planEvidence.capability_catalog_ids||[]).length?' · '+escapeHtml((planEvidence.capability_catalog_ids||[]).join('、')):'')+' · schema '+escapeHtml(planEvidence.capability_catalog_tool_schema_count||0));
      const planIdentity=planIdentityText(data); if(planIdentity) runtimeDetails.push('计划身份：'+escapeHtml(planIdentity)); const revalidationText=evidenceRevalidationText(data); if(revalidationText) runtimeDetails.push(revalidationText);
      const sources=(geometry.sources||[]).join('、')||'未声明';
      const crs=(geometry.crs||[]).join('、')||'未声明';
      $('evidenceSummary').innerHTML='<strong>证据完整性：'+(runtimeStatus==='degraded'||runtimeStatus==='unavailable'||geometryStatus==='no_geometry'||geometryStatus==='truncated_geometry'?'存在限制':'已形成')+'</strong><span>几何、运行时、数据质量与运行血缘均以本次响应为准</span>';
      const layers=(lineage.map_layers||[]).map(item=>item.dataset||item.source||item.id).filter(Boolean);
      $('lineageEvidence').className='evidence-card '+(lineage.run_id?'':'neutral');
      const registryLink=data.run_id?'<a class="evidence-reference" href="'+escapeHtml(domainPath('/runs/'+encodeURIComponent(data.run_id)+'/evidence',domainId))+'" target="_blank">查看版本化证据索引</a>':'';
      $('lineageEvidence').innerHTML='<h4>运行证据索引</h4><p>运行 ID：'+escapeHtml(lineage.run_id||data.run_id||'未生成')+'</p><p>答案：'+(lineage.answer?.available?'已形成':'未形成')+' · 轨迹：'+(lineage.trace?.available?'已形成':'未形成')+' · GeoJSON：'+(lineage.geojson?.available?'已导出':'未导出')+'</p><p>地图图层：'+escapeHtml(layers.join('、')||'暂无可引用图层')+'</p>'+registryLink+(lineage.release_evidence?.ref?'<a class="evidence-reference" href="'+escapeHtml(scopedReference(lineage.release_evidence.ref,domainId))+'" target="_blank">查看同一数据卷发布证据</a>':'');
      $('geometryEvidenceDetail').className='evidence-card '+evidenceStatusClass(geometryStatus);
      $('geometryEvidenceDetail').innerHTML='<h4>空间几何（result.geometry）</h4><p><span class="evidence-state">状态</span>'+evidenceBadge(geometryStatus)+'</p><p>可绘制：'+(geometry.available?'是':'否')+' · 要素：'+escapeHtml(geometry.feature_count||0)+' · 来源：'+escapeHtml(sources)+'</p><p>坐标系：'+escapeHtml(crs)+'</p><p>'+escapeHtml(geometry.reason||'未提供几何说明')+'</p>'+(geometryPath?'<a class="evidence-reference" href="'+escapeHtml(geometryPath)+'" target="_blank">查看或下载 GeoJSON 证据</a>':'<span class="evidence-reference">没有 GeoJSON 导出引用</span>');
      $('provenanceEvidence').className='evidence-card '+(provenanceSteps.length?'':'neutral');
      $('provenanceEvidence').innerHTML='<h4>运行血缘（provenance）</h4><p>执行策略：'+escapeHtml(p.execution_policy||'未知')+' · 步骤：'+provenanceSteps.length+' · 引用：'+escapeHtml((envelope.references||[]).length)+'</p>'+(provenanceSteps.length?'<ul class="evidence-list">'+provenanceSteps.slice(0,8).map(step=>'<li>'+escapeHtml(step.id||step.tool||'未命名步骤')+'：'+escapeHtml(step.tool||'未知工具')+' · '+escapeHtml(evidenceStatusLabel(step.status||'unknown'))+(step.result_ref?' · '+escapeHtml(step.result_ref):'')+'</li>').join('')+'</ul>':'<div class="evidence-empty">本次没有执行工具，因此没有可追溯的工具血缘。</div>');
      $('runtimeEvidence').className='evidence-card '+evidenceStatusClass(runtimeStatus);
      $('runtimeEvidence').innerHTML='<h4>运行时证据（runtime evidence）</h4><p><span class="evidence-state">数据健康</span>'+evidenceBadge(runtimeStatus)+'</p>'+(runtimeDetails.length?'<ul class="evidence-list">'+runtimeDetails.map(item=>'<li>'+escapeHtml(item)+'</li>').join('')+'</ul>':'<div class="evidence-empty">本次响应没有内嵌运行时快照；页面会尝试读取当前服务的能力快照。</div>');
      $('selectionEvidence').className='evidence-card '+evidenceStatusClass(evidenceRecovery.state|| (evidenceRegistry.available?'ready':'unavailable'));
      $('selectionEvidence').innerHTML=window.ConsoleEvidenceRegistry?.render?window.ConsoleEvidenceRegistry.render(planEvidence,evidenceRegistry,evidenceRecovery):'<h4>选择证据</h4><div class="evidence-empty">前端证据渲染模块不可用。</div>';
      $('dataEvidence').className='evidence-card '+(dataEntries.length?'':'neutral');
      $('dataEvidence').innerHTML='<h4>数据证据（data evidence）</h4>'+(dataEntries.length?'<ul class="evidence-list">'+dataEntries.slice(0,10).map(([name,item])=>{ const status=item?.status||item?.quality||'unknown'; const coverage=item?.coverage||item?.bounds; const crsText=Array.isArray(item?.crs)?item.crs.join('、'):item?.crs; return '<li><strong>'+escapeHtml(name)+'</strong> '+evidenceBadge(status)+(item?.file_count!==undefined?' · 文件 '+escapeHtml(item.file_count):item?.feature_count!==undefined?' · 要素 '+escapeHtml(item.feature_count):'')+(crsText?' · CRS '+escapeHtml(crsText):'')+(coverage?' · 已有覆盖范围证据':'')+analysisReadyText(item)+'</li>'; }).join('')+'</ul>':'<div class="evidence-empty">本次结果没有数据质量快照，不能据此推断数据已完成核验。</div>');
      const sourceBinding=analysisReady.source_binding||{};
      const outputManifest=analysisReady.output_manifest||{};
      const outputRows=Object.entries(outputManifest.outputs||{}).map(([name,item])=>'<li><strong>'+escapeHtml(name)+'</strong> '+(item.matched?'已匹配':'未匹配')+(item.reported?' · 输出 '+escapeHtml(item.reported):'')+(item.manifest?.length?' · manifest '+escapeHtml(item.manifest.join('、')):'')+'</li>').join('');
      const releaseStatus=[analysisReady.status,sourceBinding.status,outputManifest.status].some(status=>['unavailable','degraded'].includes(String(status)))?'degraded':(analysisReady.status||sourceBinding.status||outputManifest.status||'unknown');
      $('releaseEvidence').className='evidence-card release-evidence '+evidenceStatusClass(releaseStatus);
      $('releaseEvidence').innerHTML='<h4>发布完整性（metadata / source / output）</h4><div class="release-evidence-grid"><div><span class="evidence-state">元数据与网格</span>'+evidenceBadge(analysisReady.status||'unknown')+'<p>'+escapeHtml(analysisReady.derived_version||'未形成分析就绪版本')+' · '+escapeHtml((analysisReady.grid_alignment||{}).status||'未检查')+' · '+escapeHtml(verificationModeLabel(analysisReady.verification_mode))+'</p></div><div><span class="evidence-state">源绑定 SHA-256</span>'+evidenceBadge(sourceBinding.status||'unknown')+'<p>'+escapeHtml(sourceBinding.fingerprint||'未形成源数据指纹')+'</p></div><div><span class="evidence-state">输出 manifest</span>'+evidenceBadge(outputManifest.status||'unknown')+'<p>'+escapeHtml(verificationModeLabel(outputManifest.verification_mode))+' · '+(outputManifest.hashes_verified?'完整哈希已核验':'运行时未执行完整哈希')+' · mismatch '+escapeHtml(outputManifest.mismatch_count??'-')+'</p></div></div>'+(outputRows?'<ul class="evidence-list release-output-list">'+outputRows+'</ul>':'<div class="evidence-empty">没有输出文件匹配摘要。</div>')+'<a class="evidence-reference" href="'+escapeHtml(domainPath('/release-evidence?max_files=10',domainId))+'" target="_blank">下载完整三层发布报告</a>';
      const mem=data.memory_evidence||{}; $('memoryEvidence').className='evidence-card memory-evidence'+(mem.enabled?'':' neutral'); $('memoryEvidence').innerHTML='<h4>长期记忆（fact memory）</h4>'+(mem.enabled?('<p>本会话已沉淀 <b>'+escapeHtml(mem.session_fact_count||0)+'</b> 条结论记忆；后续同会话请求会把既往结论注入规划器上下文（受控、不跨会话）。</p>'):'<div class="evidence-empty">长期记忆已关闭（SPATIAL_AGENT_MEMORY_ENABLED=0）。</div>');
      const degradationMatrix=envelope.degradation||{};
      const degradationItems=Array.isArray(degradationMatrix.items)?degradationMatrix.items:[];
      if(degradationMatrix.available){
        $('degradationEvidence').innerHTML=degradationItems.length?'<div class="degradation-item '+escapeHtml(degradationMatrix.status||'warning')+'"><strong>降级与限制</strong> · '+escapeHtml(evidenceStatusLabel(degradationMatrix.status||'warning'))+' · '+escapeHtml(degradationMatrix.item_count||degradationItems.length)+' 项</div>'+degradationItems.map(item=>'<div class="degradation-item '+escapeHtml(item.severity||'warning')+'"><strong>'+escapeHtml(evidenceStatusLabel(item.severity||'warning'))+'</strong> · '+escapeHtml(item.message||'结果存在降级或限制。')+(item.source?' <small>('+escapeHtml(item.source)+')</small>':'')+'</div>').join(''):'<div class="degradation-item ok">后端结构化降级矩阵未发现明确降级状态；仍应以空间几何、数据质量和来源证据共同判断结果可信范围。</div>';
        return;
      }
      const degradations=[]; const addReason=reason=>{if(reason&&!degradations.includes(reason)) degradations.push(reason);};
      if(data.status==='NEEDS_CLARIFICATION') addReason('请求仍在澄清，尚未执行空间工具。');
      if(data.status==='FAILED'||data.status==='REJECTED'||data.status==='CANCELLED'||data.status==='TIMED_OUT') addReason('运行状态为'+statusName(data.status)+'，结果不能视为完整分析。');
      if(geometryStatus==='no_geometry') addReason('GeoJSON 引用存在但没有可绘制几何，只能查看结果摘要。');
      if(geometryStatus==='truncated_geometry') addReason('空间导出达到大小上限，地图只代表截断后的摘要。');
      if(geometryStatus==='unknown') addReason('本次运行尚未形成空间几何证据。');
      if(runtimeStatus==='degraded') addReason('运行时数据健康为部分可用，部分能力或数据集受到限制。');
      if(runtimeStatus==='unavailable') addReason('运行时数据健康为不可用，不能把演示结果当作真实数据结论。');
      if(['degraded','unavailable'].includes(String(analysisReady.status))) addReason('分析就绪派生层'+evidenceStatusLabel(analysisReady.status)+'，联合像元结果不能视为完整可复现证据。');
      if(['degraded','unavailable'].includes(String(sourceBinding.status))) addReason('源数据 SHA-256 绑定'+evidenceStatusLabel(sourceBinding.status)+'，不能确认派生层仍对应当前来源。');
      if(['degraded','unavailable'].includes(String(outputManifest.status))) addReason('派生输出 manifest'+evidenceStatusLabel(outputManifest.status)+'，输出文件与发布记录存在一致性限制。');
      if(outputManifest.status==='ready'&&outputManifest.verification_mode==='metadata'&&!outputManifest.hashes_verified) addReason('输出 manifest 当前仅完成 metadata 核验；发布前仍需显式执行输出文件 SHA-256 verifier。');
      dataEntries.forEach(([name,item])=>{ if(['degraded','unavailable','warning'].includes(String(item?.status||item?.quality))) addReason(name+' 数据证据显示为'+evidenceStatusLabel(item.status||item.quality)+'。'); (item?.checks||[]).filter(check=>check&&check.status&&check.status!=='passed').forEach(check=>addReason(name+'：'+(check.message||'数据检查未通过'))); });
      (healthResult.warnings||[]).forEach(warning=>addReason(warning));
      (data.steps||[]).forEach(step=>{if(step.status&&step.status!=='COMPLETED') addReason('工具 '+(step.tool||step.id||'未知')+' 状态为'+statusName(step.status)+'。'); const result=step.result||{}; if(result.warning) addReason(result.warning); if(result.error) addReason(result.error);});
      $('degradationEvidence').innerHTML=degradations.length?'<div class="degradation-item"><strong>降级与限制</strong></div>'+degradations.map(item=>'<div class="degradation-item">'+escapeHtml(item)+'</div>').join(''):'<div class="degradation-item ok">未发现明确降级状态；仍应以空间几何、数据质量和来源证据共同判断结果可信范围。</div>';
    }
    function renderRun(data) {
      const contract=normalizeConsoleResult(data);
      data=contract.data;
      const domainId=rememberRunDomain(data);
      lastRunData=data;
      updateResultPanels(data);
      renderPlanPreview(data);
      genericResult(data);
      setStatus(data);
      const envelope=data.result||{};
      const projection=compositeViewProjection(data);
      const projectedAnswer=projection?.answer||{};
      $('title').textContent=projectedAnswer.headline||envelope.title||data.plan?.goal||statusName(data.status);
      $('subtitle').textContent=projectedAnswer.summary||envelope.summary||data.resolved_request||data.request;
      $('decisionMode').textContent=decisionMode(data);
      $('answer').textContent=projectedAnswer.summary||envelope.summary||data.answer||'暂无最终答案。';
      $('answer').className='answer'+(projectedAnswer.summary||envelope.summary||data.answer?'':' muted');
      const projectionRenderer=window.ConsoleResultProjection;
      if(projectionRenderer&&typeof projectionRenderer.normalize==='function'&&typeof projectionRenderer.render==='function'){
        const projectionModel=projectionRenderer.normalize(data);
        $('answerProjection').innerHTML=projectionRenderer.render(projectionModel,{escapeHtml});
        $('answerProjection').hidden=false;
      } else {
        $('answerProjection').innerHTML='';
        $('answerProjection').hidden=true;
      }
      const errorCategory=data.error_category||(data.result||{}).error_category;
      const safeError=String(data.status||'')==='REJECTED'?'请求已拒绝，详见决策证据。':String(data.status||'')==='NEEDS_CLARIFICATION'?'需要补充信息，详见决策证据。':String(errorCategory||'').toLowerCase()==='provider'?'模型服务不可用，原始服务错误未在前端展示。':data.error;
      $('error').innerHTML=safeError?('<div class="error">'+errorCategoryBadge(errorCategory)+escapeHtml(safeError)+'</div>'):'';
      if(!projectionRenderer) renderClarification(data);
      $('decisionEvidence').innerHTML=renderDecisionEvidence(data);
      $('goal').textContent=data.plan?.goal||'尚未生成任务计划。';
      metrics(data);
      steps(data);
      provenance(data);
      trace(data);
      renderEvidence(data);
      const links=[];
      const retryLineage=(data.result||{}).lineage?.retry;
      if(retryLineage?.available) links.push('<span class="retry-note">本结果为第 '+escapeHtml(retryLineage.count)+' 次重试后的运行详情（沿用原运行 ID，未重新规划）</span>');
      const replanEvidence=(envelope.replanning&&Array.isArray(envelope.replanning.events))?envelope.replanning.events:null;
      const replanEvents=(replanEvidence||data.replan_events||[]).filter(item=>item&&item.failed_step_id);
      if(replanEvents.length) links.push('<span class="retry-note replan-note">执行中自适应重规划 '+escapeHtml(replanEvents.length)+' 次：失败步骤 '+escapeHtml(replanEvents.map(item=>item.failed_step_id).join('、'))+' 后由规划器重排剩余步骤完成（'+escapeHtml(replanEvents.map(item=>'新增 '+String((item.replanned_step_ids||[]).length)+' 步').join('、'))+'）</span>');
      if(data.status==='FAILED'&&data.run_id) links.push('<button class="retry-action" type="button" onclick="retryRun(\''+escapeHtml(data.run_id)+'\')">重试失败步骤</button>');
      const runArtifactPath=artifactReferencePath(envelope.artifacts?.run||data.artifact_reference,data.artifact_ref,'runs',domainId);
      if(runArtifactPath) links.push('<a href="'+escapeHtml(runArtifactPath)+'" target="_blank">打开 JSON 运行记录</a>');
      const geojsonReference=envelope.geometry?.reference||envelope.artifacts?.geometry||{};
      const geojsonRef=geojsonReference.ref||data.geojson_ref;
      const geojsonPath=geometryArtifactPath(geojsonReference,geojsonRef,domainId);
      if(geojsonPath) {
        links.push('<a download href="'+escapeHtml(geojsonPath)+'">下载 GeoJSON</a>');
      }
      $('links').innerHTML=links.join('');
      updateResultPanels(data);
      loadRuntimeEvidence(domainId);
    }
    function loadRuntimeEvidence(domainId=currentDomainId()) { if(domainId===AUTO_DOMAIN_VALUE||runtimeEvidenceSnapshot||runtimeEvidencePromise) return; const generation=domainGeneration; runtimeEvidencePromise=nativeFetch(domainPath('/capabilities/runtime?max_files=3',domainId)).then(response=>{if(!response.ok) throw new Error('runtime evidence unavailable');return response.json();}).then(snapshot=>{if(generation!==domainGeneration||domainId!==currentDomainId()) return; runtimeEvidenceSnapshot=snapshot;if(lastRunData&&responseDomain(lastRunData)===domainId) renderEvidence(lastRunData);}).catch(()=>null).finally(()=>{runtimeEvidencePromise=null;}); }
    function renderCapabilities(data) { const catalog=data.capability_catalog||data||{}; const items=catalog.capabilities||[]; const ready=items.filter(item=>item.dataset_gate==='ready'&&item.environment_supported).length; const unknown=items.filter(item=>item.dataset_gate==='unknown').length; const actions=(catalog.actions?.actions||actionCatalog.actions||[]).length; $('capabilityStatus').textContent='能力目录：'+ready+' / '+items.length+' 项已通过数据门控'+(unknown?'；'+unknown+' 项待健康检查':'')+'；已注册动作 '+actions+' 项；真实几何以运行证据为准。'; }
    function capabilityHealthLabel(id) { return String(id||'').replace(/_/g,' ').replace(/\b\w/g,letter=>letter.toUpperCase()); }
    function renderHealth(data) { health=data; const caps=data.capabilities||{}; const rows=Object.entries(caps).filter(([id,value])=>typeof value==='boolean'&&!['live_llm','live_llm_configured'].includes(id)).slice(0,8).map(([id,available])=>[capabilityHealthLabel(id),available?'可用':'不可用',available]); rows.push(llmHealthLabel(caps)); $('env').innerHTML=rows.map(x=>'<div class="'+(x[2]?'':'bad')+'">'+escapeHtml(x[0])+'：'+escapeHtml(x[1])+'</div>').join(''); renderCapabilities(data); }
    async function loadHealth() { try { const response=await fetch('/health'); renderHealth(await response.json()); } catch(e) { $('env').innerHTML='<div class="bad">无法读取运行环境状态</div>'; $('capabilityStatus').textContent='能力目录暂不可用。'; } }
    async function loadCapabilities(domainId=currentDomainId()) { try { const query='?planner='+encodeURIComponent($('planner').value)+'&backend='+encodeURIComponent($('backend').value); const response=await nativeFetch(domainPath('/capabilities',domainId)+query); const data=await response.json(); if(!response.ok) throw new Error(responseError(data,'能力目录不可用')); if(domainId===currentDomainId()) renderCapabilities(data); } catch(error) { if(domainId===currentDomainId()) $('capabilityStatus').textContent='当前领域能力目录暂不可用：'+error.message; } }
    function renderToolApprovals(data) {
      const renderer=window.ConsoleToolApprovals;
      if(!renderer||typeof renderer.mount!=='function') { $('toolApprovals').innerHTML='<div class="tool-governance-empty">工具治理投影模块不可用。</div>'; return; }
      const model=renderer.mount({target:$('toolApprovals'),payload:data,escapeHtml,onAction:resolveToolApproval});
      $('toolGovernanceMeta').textContent=model.items.length?'共 '+model.items.length+' 条审批记录':'暂无审批记录';
    }
    async function loadToolApprovals(domainId=currentDomainId()) {
      if(domainId===AUTO_DOMAIN_VALUE) return;
      try {
        const response=await nativeFetch(domainPath('/tools/approvals?limit=32',domainId));
        const data=await response.json().catch(()=>({}));
        if(!response.ok) throw new Error(responseError(data,'审批状态暂不可用'));
        if(domainId===currentDomainId()) renderToolApprovals(data);
      } catch(error) {
        if(domainId===currentDomainId()) {
          $('toolGovernanceMeta').textContent='暂不可用';
          $('toolApprovals').innerHTML='<div class="tool-governance-empty">'+escapeHtml(error.message)+'。</div>';
        }
      }
    }
    async function resolveToolApproval(item, action) {
      const domainId=item.domain_id||currentDomainId();
      const body=withDomainPayload({action,expected_version:item.version,receipt_fingerprint:item.receipt_fingerprint,actor_id:'console'},domainId);
      const response=await nativeFetch(domainPath('/tools/approvals/'+encodeURIComponent(item.approval_id)+'/resolve',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(responseError(data,'审批动作失败'));
      await loadToolApprovals(domainId);
    }
    function actionSpec(actionId) { return (actionCatalog.actions||[]).find(item=>item&&item.id===actionId)||null; }
    function renderActionWorkbench() { if(!window.ConsoleActionHost){ $('actionWorkbenchBody').innerHTML='<div class="distribution-note">Action Host 不可用。</div>'; return; } window.ConsoleActionHost.mount({target:$('actionWorkbenchBody'),catalog:actionCatalog,initialValues:{planner:$('planner').value,backend:$('backend').value},invoke:executeDomainAction,onResult:async(data,action)=>{ if(responseDomain(data)!==currentDomainId()) return; setStatus(data.status||'COMPLETED'); appendMessage('assistant',answerText(data)||action.label+' 已完成'); renderActionExecution(data); $('actionWorkbench').open=false; loadHistory(responseDomain(data)); }}); }
    async function loadActions(domainId=currentDomainId()) { const generation=domainGeneration; const query='?planner='+encodeURIComponent($('planner').value)+'&backend='+encodeURIComponent($('backend').value); const promise=nativeFetch(domainPath('/actions',domainId)+query).then(async response=>{ if(!response.ok) throw new Error('action catalog unavailable'); const data=await response.json(); const catalog={schema_version:data.schema_version||'spatial-agent.actions.v1',domain_id:data.domain_id||domainId,actions:Array.isArray(data.actions)?data.actions:[]}; if(generation===domainGeneration&&domainId===currentDomainId()){ actionCatalog=catalog; renderActionWorkbench(); } return catalog; }).catch(()=>{ const catalog={schema_version:'spatial-agent.actions.v1',domain_id:domainId,actions:[]}; if(generation===domainGeneration&&domainId===currentDomainId()){ actionCatalog=catalog; renderActionWorkbench(); } return catalog; }).finally(()=>{ if(actionCatalogPromise===promise) actionCatalogPromise=null; }); actionCatalogPromise=promise; return promise; }
    async function executeDomainAction(actionId,payload) { const domainId=currentDomainId(); if(actionCatalogPromise) await actionCatalogPromise; if(domainId!==currentDomainId()) throw new Error('领域已切换，请在新领域重新选择动作。'); if(!actionSpec(actionId)) await loadActions(domainId); if(!actionSpec(actionId)) throw new Error('当前领域未注册动作：'+actionId); const body=withDomainPayload(payload||{},domainId); const response=await nativeFetch(domainPath('/actions/'+encodeURIComponent(actionId),domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const data=await response.json().catch(()=>({})); if(!response.ok) throw new Error(responseError(data,'动作执行失败')); const executionId=data.action_execution_id||data.result?.lineage?.action_execution?.ref; if(executionId) actionDomains.set(String(executionId),responseDomain(data,domainId)); return data; }
    async function openRunDetail(runId,domainId=domainForRun(runId)) { if(!runId) return; $('error').innerHTML=''; try { const response=await nativeFetch(domainPath('/runs/'+encodeURIComponent(runId),domainId)+'?planner='+encodeURIComponent($('planner').value)+'&backend='+encodeURIComponent($('backend').value)); if(!response.ok){ const body=await response.json().catch(()=>({})); throw new Error(responseError(body,'运行详情不可用（HTTP '+response.status+'）')); } const data=await response.json(); rememberRunDomain(data,domainId); const sessionId=data.session_id; if(sessionId&&domainId===currentDomainId()){ const option=[...$('session').options].find(item=>item.value===sessionId); if(!option) addConversationOption({session_id:sessionId,display_name:'对话'+($('session').options.length+1)},domainId); $('session').value=sessionId; $('chatMeta').textContent='当前对话：'+selectedConversationLabel(); } resetConversationView(); appendMessage('user',data.request||'未命名任务'); appendMessage('assistant',answerText(data)||'未知状态',data.run_id); renderRun(data); } catch(error) { $('error').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>'; } }
    async function openActionDetail(executionId,domainId=domainForAction(executionId)) { if(!executionId) return; try { const response=await nativeFetch(domainPath('/action-executions/'+encodeURIComponent(executionId),domainId)); if(!response.ok){ const body=await response.json().catch(()=>({})); throw new Error(responseError(body,'Action 详情不可用（HTTP '+response.status+'）')); } const data=await response.json(); data._console_domain_id=domainId; actionDomains.set(String(executionId),domainId); resetConversationView(); appendMessage('assistant','已恢复 Action：'+(data.action_id||'未知动作')); renderActionExecution(data); } catch(error) { $('error').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>'; } }
    function renderActionExecution(data) { lastRunData=data; const envelope=data.result||{}; $('resultEmpty').style.display='none'; setResultPanel('.common-result',false); setResultPanel('.answer-result',true); const hasTrace=Boolean((data.trace_summary||[]).length); setResultPanel('.trace-result',hasTrace); $('title').textContent='Action：'+(data.action_id||envelope.action?.id||'未知'); $('subtitle').textContent=envelope.summary||'已从 artifact 恢复 Action 结果，未重新执行。'; $('decisionMode').textContent='Domain Action · 结构化执行'; $('answer').textContent=envelope.summary||data.error||'已恢复结构化 Action 结果。'; $('answer').className='answer'; $('answerProjection').innerHTML=''; $('answerProjection').hidden=true; $('error').innerHTML=data.error?'<div class="error">'+escapeHtml(data.error)+'</div>':''; genericResult(data); $('trace').innerHTML=(data.trace_summary||[]).map(item=>'<li>'+escapeHtml(item)+'</li>').join('')||'<li class="muted">暂无 Action 轨迹。</li>'; $('links').innerHTML=renderActionEvidence(data); $('goal').textContent='Action 结果类型：'+escapeHtml(envelope.type||data.result_type||'unknown'); setResultPanel('.evidence-result',false); setResultPanel('.plan-preview-result',false); setResultPanel('.workflow-evidence-result',false); setAdvancedVisibility(hasTrace, hasTrace?'Action 执行轨迹':'暂无高级执行详情', false); }
    async function restoreSession(domainId=currentDomainId()) {
      const sessionId=$('session').value;
      const viewGeneration=conversationGeneration;
      if(!sessionId||domainId!==currentDomainId()||(sessionDomains.get(sessionId)&&sessionDomains.get(sessionId)!==domainId)) return;
      resetConversationView();
      $('chatMeta').textContent='当前对话：'+selectedConversationLabel();
      try {
        const response=await nativeFetch(domainPath('/sessions/'+encodeURIComponent(sessionId)+'/runs?limit=20',domainId));
        if(!response.ok) throw new Error('会话历史读取失败');
        const data=await response.json();
        if(viewGeneration!==conversationGeneration||domainId!==currentDomainId()||sessionId!==$('session').value) return;
        const runs=(data.runs||[]).slice().reverse();
        if(!runs.length){ welcome(); return; }
        runs.forEach(item=>{ rememberRunDomain(item,domainId); appendMessage('user',item.request||'未命名任务'); appendMessage('assistant',item.answer||item.error||statusName(item.status||'未知'),item.run_id); });
        const latest=data.runs[0];
        if(latest?.run_id){ const detail=await nativeFetch(domainPath('/runs/'+encodeURIComponent(latest.run_id),domainId)+'?planner='+encodeURIComponent($('planner').value)+'&backend='+encodeURIComponent($('backend').value)); if(detail.ok&&viewGeneration===conversationGeneration&&domainId===currentDomainId()&&sessionId===$('session').value){ const detailData=await detail.json(); if(viewGeneration!==conversationGeneration) return; rememberRunDomain(detailData,domainId); renderRun(detailData); } }
      } catch(error) { if(viewGeneration===conversationGeneration&&domainId===currentDomainId()&&sessionId===$('session').value){ welcome(); appendMessage('system',error.message); } }
    }
    async function loadHistory(domainId=currentDomainId()) {
      try {
        const [historyResponse,metricsResponse,actionResponse]=await Promise.all([nativeFetch(domainPath('/runs?limit=20',domainId)),nativeFetch(domainPath('/metrics',domainId)),nativeFetch(domainPath('/action-executions?limit=20',domainId))]);
        if(!historyResponse.ok) throw new Error('历史任务读取失败');
        const data=await historyResponse.json();
        const metricsData=metricsResponse.ok?await metricsResponse.json():null;
        const actionData=actionResponse.ok?await actionResponse.json():{actions:[]};
        if(domainId!==currentDomainId()) return;
        if(metricsData) $('runtimeMetrics').textContent='累计运行 '+metricsData.run_count+' 次 · 总令牌 '+(metricsData.total_tokens||0)+' · Action '+(metricsData.actions?.count||0)+' 次';
        const runs=data.runs||[],actions=actionData.actions||[];
        runs.forEach(item=>rememberRunDomain(item,domainId));
        actions.forEach(item=>{ if(item.action_execution_id) actionDomains.set(String(item.action_execution_id),domainId); });
        const runHtml=runs.map(item=>{ const runId=escapeHtml(item.run_id||''); const request=escapeHtml(item.request||'未命名任务'); const registry=item.evidence_registry||{}; const registryText=registry.schema_version?' · 证据 '+escapeHtml(registry.entry_count||0)+' 项':''; const registryLink=runId?'<a href="'+escapeHtml(domainPath('/runs/'+encodeURIComponent(item.run_id)+'/evidence',domainId))+'" target="_blank">索引</a>':''; const mainAction=runId?'data-history-run="'+runId+'"':'data-history-request="'+request+'"'; const mainTitle=runId?'打开该次运行的完整详情（不重新执行模型）':'重新执行该请求'; return '<div class="history-item"><div class="history-item-main"><button type="button" class="history-open" '+mainAction+' title="'+mainTitle+'">'+request+'</button>'+(runId?'<button type="button" class="history-rerun" data-history-request="'+request+'" title="重新执行该请求（会再次调用模型）">重跑</button>':'')+'</div><small>'+escapeHtml(statusName(item.status||'未知'))+' · '+runId+registryText+(registryLink?' · '+registryLink:'')+'</small></div>'; }).join('');
        const actionHtml=actions.map(item=>{ const executionId=escapeHtml(item.action_execution_id||''); return '<div class="history-item"><div class="history-item-main"><button type="button" class="history-open" data-action-execution="'+executionId+'" title="从 artifact 恢复 Action，不重新执行">动作：'+escapeHtml(item.action_id||'未知')+'</button></div><small>'+escapeHtml(statusName(item.status||'未知'))+' · '+escapeHtml(item.domain_id||domainId)+' · '+executionId+'</small></div>'; }).join('');
        $('historyList').innerHTML=runHtml+actionHtml||'<div class="muted">暂无历史任务。</div>';
        $('historyList').querySelectorAll('[data-history-run]').forEach(button=>button.addEventListener('click',()=>openRunDetail(button.getAttribute('data-history-run'),domainId)));
        $('historyList').querySelectorAll('[data-history-request]').forEach(button=>button.addEventListener('click',()=>sendChat(button.getAttribute('data-history-request'))));
        $('historyList').querySelectorAll('[data-action-execution]').forEach(button=>button.addEventListener('click',()=>openActionDetail(button.getAttribute('data-action-execution'),domainId)));
      } catch(error) { if(domainId===currentDomainId()){ $('historyList').innerHTML='<div class="muted">历史任务暂不可用。</div>'; $('runtimeMetrics').textContent='运行指标暂不可用。'; } }
    }
    function validateSelection(request) { const caps=health.capabilities||{}; if(!String(request||'').trim()) throw new Error('请输入问题后再发送。'); if($('planner').value==='openai'&&!caps.live_llm_configured) throw new Error('当前服务没有可用的大模型配置。请先配置本地模型配置或环境变量。'); if($('planner').value==='openai'&&!caps.live_llm_network) throw new Error('当前服务进程不能访问大模型网络。请从允许出站网络的终端重新启动服务，或先切回规则规划器。'); }
     async function retryRun(runId) { const domainId=domainForRun(runId); setStatus('EXECUTING'); $('subtitle').textContent='正在从失败步骤恢复，已完成步骤不会重复执行。'; try { const body=withDomainPayload({planner:$('planner').value,backend:$('backend').value,export_artifact:true,export_geojson:true},domainId); const response=await nativeFetch(domainPath('/runs/'+encodeURIComponent(runId)+'/retry',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const data=await response.json(); if(!response.ok) throw new Error(responseError(data,'重试失败')); rememberRunDomain(data,domainId); if(domainId===currentDomainId()){ if(data.run_id&&['SUBMITTED','QUEUED','PLANNING','EXECUTING'].includes(String(data.status||'').toUpperCase())) startLiveRun(data,data.request||'重试失败步骤',domainId); else { renderRun(data); appendMessage('assistant',answerText(data),data.run_id); } } } catch(e) { if(domainId===currentDomainId()){ setStatus('FAILED'); $('error').innerHTML='<div class="error">'+escapeHtml(e.message)+'</div>'; appendMessage('system',e.message); } } }
    async function resolveRunDecision(decisionId, choice, version) { if(!decisionId) return; const domainId=decisionDomains.get(String(decisionId))||responseDomain(lastRunData); document.querySelectorAll('.decision-action-bar button').forEach(button=>button.disabled=true); try { const body=withDomainPayload({choice,expected_version:version,planner:$('planner').value,backend:$('backend').value},domainId); const response=await nativeFetch(domainPath('/decisions/'+encodeURIComponent(decisionId)+'/resolve',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const data=await response.json().catch(()=>({})); if(!response.ok) throw new Error(responseError(data,'决策提交失败')); rememberRunDomain(data,domainId); if(domainId===currentDomainId()){ renderRun(data); appendMessage('assistant',answerText(data),data.run_id); } } catch(error){ if(domainId===currentDomainId()){ $('error').innerHTML='<div class="error">'+escapeHtml(error.message)+'</div>'; document.querySelectorAll('.decision-action-bar button').forEach(button=>button.disabled=false); } } }
    const interactionCommandKeys=new Map();
    function interactionCommandKey(model,actionId){
      const subject=model.subject||{},current=subject.current||{};
      const identity=[current.kind,current.id,subject.revision,actionId].join(':');
      if(!interactionCommandKeys.has(identity)){
        const nonce=(globalThis.crypto&&typeof globalThis.crypto.randomUUID==='function')?globalThis.crypto.randomUUID():(Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
        interactionCommandKeys.set(identity,('console:'+String(current.id||'interaction').slice(0,40)+':'+String(actionId).slice(0,24)+':'+nonce).slice(0,128));
      }
      return interactionCommandKeys.get(identity);
    }
    async function invokeCanonicalInteraction(model,actionId,input,data){
      if(!window.ConsoleInteraction) throw new Error('统一交互契约模块不可用。');
      const command=window.ConsoleInteraction.command(model,actionId,input,interactionCommandKey(model,actionId));
      const current=model.subject.current||{};
      if(current.kind==='routing_decision'){
        const pending=domainRoutingRequests.get(String(current.id));
        if(!pending) throw new Error('领域路由上下文已失效，请重新提交请求。');
        const body=Object.assign({},command,{session_id:pending.payload.session_id});
        const response=await nativeFetch('/domain-routing/decisions/'+encodeURIComponent(current.id)+'/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        let result=await response.json().catch(()=>({}));
        if(!response.ok) throw new Error(responseError(result,'领域选择提交失败'));
        const selectedDomain=result.domain_id||result.domain_routing?.selection?.domain_id||String(input?.domain_id||'');
        if(!result.run_id){
          const overrideDecisionId=result.domain_routing?.decision_id||result.domain_routing_decision_id;
          if(!overrideDecisionId) throw new Error('领域选择响应缺少 override decision identity。');
          const runPayload=Object.assign({},pending.payload,{domain_id:undefined,domain_routing_decision_id:overrideDecisionId});
          const runResponse=await nativeFetch('/runs/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(runPayload)});
          result=await runResponse.json().catch(()=>({}));
          if(!runResponse.ok) throw new Error(responseError(result,'所选领域执行失败'));
        }
        if(result.run_id&&['SUBMITTED','QUEUED','PLANNING','EXECUTING'].includes(String(result.status||'').toUpperCase())) result=await pollQueuedRun(result,pending.payload,selectedDomain);
        bindAutoDomain(result,selectedDomain);
        rememberRunDomain(result,selectedDomain);
        domainRoutingRequests.delete(String(current.id));
        return result;
      }
      if(current.kind!=='run'||!current.id) throw new Error('当前交互没有可执行的运行主体。');
      const domainId=model.subject.domain_id||domainForRun(current.id)||responseDomain(data);
      const body=withDomainPayload(Object.assign({},command,{planner:$('planner').value,backend:$('backend').value}),domainId);
      const response=await nativeFetch(domainPath('/runs/'+encodeURIComponent(current.id)+'/interaction',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const result=await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(responseError(result,'交互动作提交失败'));
      rememberRunDomain(result,domainId);
      return result;
    }
    function renderCanonicalInteraction(data){
      if(!window.ConsoleInteraction||!window.ConsoleActionHost) return false;
      const model=window.ConsoleInteraction.normalize(data);
      const present=data?.interaction?.schema_version===window.ConsoleInteraction.VERSION||data?.result?.interaction?.schema_version===window.ConsoleInteraction.VERSION;
      if(!present||(!model.actionable&&model.state!=='unavailable')) return false;
      const current=model.subject.current||{};
      if(current.kind==='routing_decision'){
        domainRoutingRequests.set(String(current.id),{request:data._console_auto_request||data.request||'',payload:Object.assign({},data._console_auto_payload||{})});
      }
      const labels={domain_selection:'选择处理领域',workflow_selection:'选择执行能力',facts_collection:'补充执行信息',plan_confirmation:'确认执行计划',plan_repair:'修复执行计划',recovery:'恢复运行',lifecycle:'运行控制'};
      const candidates=window.ConsoleInteraction.candidates(model);
      const candidateHtml=candidates.length?'<div class="selection-candidate-grid">'+candidates.map(item=>'<article class="selection-candidate"><h4>'+escapeHtml(item.label||item.id)+'</h4><p><code>'+escapeHtml(item.id)+'</code></p>'+(item.description?'<small>'+escapeHtml(item.description)+'</small>':'')+(item.capability_ids.length?'<small>能力：'+escapeHtml(item.capability_ids.join('、'))+'</small>':'')+'</article>').join('')+'</div>':'';
      const missing=(Array.isArray(model.content.missing_fields)?model.content.missing_fields:[]).map(item=>item&&(item.label||item.id)).filter(Boolean).slice(0,16);
      const blocked=model.blocked_actions.length?'<small class="selection-lineage">已阻断动作：'+escapeHtml(model.blocked_actions.join('、'))+'</small>':'';
      const receipt=model.receipt?'<small class="selection-lineage">动作凭据：'+escapeHtml(model.receipt.action_id||model.receipt.action||'未知')+' · '+escapeHtml(model.receipt.status||'UNKNOWN')+(model.receipt.reused?' · 已复用':'')+'</small>':'';
      const lineageCount=Number(model.lineage.repair_count||model.lineage.event_count||0);
      const lineage=lineageCount?'<small class="selection-lineage">交互链：'+escapeHtml(lineageCount)+' 个历史事件</small>':'';
      const html='<section class="selection-interaction-card" data-interaction-state="'+escapeHtml(model.state)+'" data-interaction-kind="'+escapeHtml(model.kind)+'" data-schema-version="'+escapeHtml(model.schema_version)+'"><div class="selection-interaction-head"><strong>'+escapeHtml(labels[model.kind]||'下一步交互')+'</strong><span>'+escapeHtml(model.reason_code)+'</span></div>'+(missing.length?'<p>待补充：'+escapeHtml(missing.join('、'))+'</p>':'')+blocked+receipt+lineage+candidateHtml+(model.actions.length?'<div data-canonical-action-host data-schema-version="'+escapeHtml(model.schema_version)+'"></div>':'<p class="distribution-note">当前没有可安全执行的后续动作，请补充问题范围后重新提交。</p>')+'</section>';
      const panel=$('decisionEvidence');
      panel.insertAdjacentHTML('afterbegin',html);
      setResultPanel('.decision-evidence-result',true);
      const target=panel.querySelector('[data-canonical-action-host]');
      if(!target) return true;
      window.ConsoleActionHost.mount({
        target,
        catalog:window.ConsoleInteraction.catalog(model),
        invoke:(actionId,input)=>invokeCanonicalInteraction(model,actionId,input,data),
        onResult:async result=>{ renderRun(result); appendMessage('assistant',answerText(result),result.run_id); await hydrateAutoDomainState(result); },
      });
      return true;
    }
    const baseRenderRunForInteraction = renderRun;
    renderRun = function(data) {
      baseRenderRunForInteraction(data);
      renderCanonicalInteraction(data);
    };
    function matchingPreviewFingerprint(request, workflow, domainContext) { if(!lastPlanPreview?.fingerprint) return null; const same=lastPlanPreview.request===request&&lastPlanPreview.session_id===$('session').value&&lastPlanPreview.domain_id===currentDomainId()&&lastPlanPreview.planner===$('planner').value&&lastPlanPreview.backend===$('backend').value&&lastPlanPreview.workflow===JSON.stringify(workflow||null)&&lastPlanPreview.domain_context===JSON.stringify(domainContext||{}); return same?lastPlanPreview.fingerprint:null; }
    async function sendChat(text) {
      const request=(text ?? $('prompt').value).trim();
      if(!request) return;
      const button=$('send'),mode=selectedDomainModeId(),generation=domainGeneration;
      const viewGeneration=conversationGeneration;
      const unboundAuto=mode===AUTO_DOMAIN_VALUE&&!autoDomainBinding;
      const domainId=currentDomainId();
      let sessionId=unboundAuto?ensureAutoDraftSessionId():($('session').value||autoDomainBinding?.session_id||'');
      if(!unboundAuto&&(!sessionId||sessionDomains.get(sessionId)!==domainId)){ const session=await newSession(domainId,false); sessionId=session?.session_id||$('session').value; }
      button.disabled=true;
      $('prompt').value='';
      $('chatMeta').textContent='当前对话：'+selectedConversationLabel();
      appendMessage('user',request);
      setStatus('PLANNING');
      $('title').textContent='正在分析';
      $('subtitle').textContent='规划器和运行时正在处理请求。';
      $('error').innerHTML='';
      try {
        validateSelection(request);
        const workflow=await validateWorkflowSelection();
        if(mode!==selectedDomainModeId()||generation!==domainGeneration) throw new Error('领域已切换，本次请求未提交。');
        const domainContext=rendererRegistry?.context()||{};
        const preview_fingerprint=matchingPreviewFingerprint(request,workflow,domainContext);
        const requestPayload=Object.assign({request,session_id:sessionId||undefined,planner:$('planner').value,backend:$('backend').value,workflow,preview_fingerprint,require_confirmation:$('requireConfirmation').checked,export_artifact:true,export_geojson:true},domainContext);
        if(unboundAuto) requestPayload.async=true;
        const payload=unboundAuto?requestPayload:withDomainPayload(requestPayload,domainId);
        const response=await fetch(unboundAuto?'/runs/auto':domainPath('/runs',domainId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const data=await response.json();
        if(!response.ok) throw new Error(responseError(data,'请求失败'));
         if(unboundAuto&&data.status==='NEEDS_CLARIFICATION'){ data._console_auto_request=request; data._console_auto_payload=payload; }
         const responseDomainId=data.domain_id||domainId;
         if(unboundAuto&&data.domain_id) bindAutoDomain(data,data.domain_id);
         rememberRunDomain(data,responseDomainId);
         if(mode===selectedDomainModeId()&&generation===domainGeneration&&viewGeneration===conversationGeneration){
           if(data.run_id&&['SUBMITTED','QUEUED','PLANNING','EXECUTING'].includes(String(data.status||'').toUpperCase())) startLiveRun(data,request,responseDomainId);
           else { renderRun(data); appendMessage('assistant',answerText(data),data.run_id); }
           if(unboundAuto&&data.domain_id) await hydrateAutoDomainState(data);
         }
       } catch(e) {
        if(mode===selectedDomainModeId()&&generation===domainGeneration&&viewGeneration===conversationGeneration){ setStatus('FAILED'); $('resultEmpty').style.display='none'; setResultPanel('.answer-result',true); $('error').innerHTML='<div class="error">'+escapeHtml(e.message)+'</div>'; appendMessage('system',e.message); }
       } finally { button.disabled=Boolean(activeRunId)||window.__consoleDomainReady===false; $('prompt').focus(); }
    }
    $('send').addEventListener('click',()=>sendChat());
    $('previewPlan').addEventListener('click',previewPlan);
    $('prompt').addEventListener('keydown',event=>{ if(event.key==='Enter'&&!event.shiftKey){ event.preventDefault(); sendChat(); } });
    $('session').addEventListener('change',()=>{
      conversationGeneration++;
      if(usesAutoRouting()&&!autoDomainBinding) {
        autoDraftSessionId=$('session').value||'';
        resetConversationView();
        welcome();
        return;
      }
      restoreSession(currentDomainId());
    });
    $('domain').addEventListener('change',()=>{ const nextMode=selectedDomainModeId(); autoDraftSessionId=''; domainRoutingRequests.clear(); if(nextMode===AUTO_DOMAIN_VALUE){ const available=new Set((domainCatalog.domains||[]).map(item=>String(item.id))); const sessionId=$('session').value,domainId=sessionDomains.get(sessionId); autoDomainBinding=preferredAutoDomainBinding(available)||(domainId?{domain_id:domainId,session_id:sessionId}:null); } else autoDomainBinding=null; persistAutoDomainBinding(); resetConversationView(); persistSelectedDomain(); reloadDomainContext(); });
    $('newSession').addEventListener('click',()=>newSession());
    $('deleteSession').addEventListener('click',deleteConversation);
    $('clearAllSessions').addEventListener('click',()=>clearAllSessions());
    $('refreshHistory').addEventListener('click',()=>{ if(!usesAutoRouting()||autoDomainBinding) loadHistory(currentDomainId()); });
    $('clearChat').addEventListener('click',clearChat);
    $('workflow').addEventListener('change',renderWorkflowEditor);
    $('planner').addEventListener('change',()=>{ if(usesAutoRouting()&&!autoDomainBinding) return; const domainId=currentDomainId(); loadActions(domainId); loadCapabilities(domainId); loadWorkflows(domainId); });
    $('backend').addEventListener('change',()=>{ if(usesAutoRouting()&&!autoDomainBinding) return; const domainId=currentDomainId(); loadActions(domainId); loadCapabilities(domainId); loadWorkflows(domainId); });
    window.__consoleBootstrapReady = false;
    (async()=>{
      await Promise.all([loadHealth(),loadDomains()]);
      await reloadDomainContext();
      window.__consoleBootstrapReady = true;
    })().catch(error=>{
      $('error').innerHTML='<div class="error">控制台初始化失败：'+escapeHtml(error.message)+'</div>';
      window.__consoleBootstrapReady = true;
      window.__consoleDomainReady = true;
    });
    $('cancelRun').addEventListener('click',cancelActiveRun);
