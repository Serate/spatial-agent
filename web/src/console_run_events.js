(function (global) {
  'use strict';

  const TERMINAL_STATUSES = new Set([
    'COMPLETED', 'PARTIAL', 'FAILED', 'REJECTED', 'BLOCKED', 'CANCELLED', 'TIMED_OUT',
  ]);
  const TERMINAL_KINDS = new Set(['run_completed', 'run_failed', 'run_cancelled', 'run_timed_out']);
  const RUN_EVENT_SCHEMA_VERSION = 'spatial-agent.run-event.v1';
  const EVENT_KINDS = new Set([
    'run_started', 'stage_started', 'stage_progress', 'stage_completed', 'stage_failed',
    'tool_started', 'tool_completed', 'tool_failed', 'heartbeat',
    'answer_delta', 'run_completed', 'run_failed', 'run_waiting', 'run_finished',
    'react_turn_started', 'react_action_accepted', 'react_action_completed',
    'react_action_blocked', 'react_waiting_for_approval', 'react_finished',
    'retry_started', 'recovery_started', 'run_timed_out', 'run_cancelled',
  ]);
  const EVENT_PHASES = new Set(['resolve', 'clarify', 'plan', 'validate', 'execute', 'answer', 'evidence']);
  const EVENT_STATUSES = new Set([
    'CREATED', 'QUEUED', 'PLANNING', 'PLANNED', 'EXECUTING',
    'WAITING_FOR_DECISION', 'COMPLETED', 'NEEDS_CLARIFICATION', 'REJECTED',
    'FAILED', 'CANCELLED', 'TIMED_OUT', 'PENDING', 'RUNNING', 'BLOCKED',
  ]);
  const ALLOWED_DATA = new Set([
    'tool', 'step_id', 'stage_index', 'stage_count', 'current_step', 'total_steps',
    'attempt', 'retryable', 'duration_ms', 'event_count', 'recovery_count',
    'error_category', 'answer_length', 'streaming', 'provider',
    'answer_delta', 'reason_code', 'cursor', 'fallback', 'source',
    'artifact_available', 'result_type', 'run_duration_ms', 'elapsed_ms',
    'summary', 'turn_index', 'action', 'action_id', 'validation_state',
    'output_type', 'action_count', 'max_actions', 'max_turns', 'request_mode',
    'request_mode_reason', 'tool_count', 'execution_started',
    'phase_elapsed_ms', 'run_elapsed_ms', 'phase_budget_ms',
    'run_budget_remaining_ms', 'total_budget_ms', 'phase_remaining_ms',
    'retry_count', 'heartbeat_count', 'budget_state', 'resume_available',
    'recovery_action', 'recovery_actions',
  ]);
  const MAX_ANSWER_DELTA = 512;
  const PHASE_LABELS = Object.freeze({
    resolve: '理解请求',
    clarify: '补充信息',
    plan: '生成计划',
    validate: '校验计划',
    execute: '执行工具',
    answer: '汇总答案',
    evidence: '整理证据',
  });
  const KIND_LABELS = Object.freeze({
    run_started: '已接收请求',
    stage_started: '阶段开始',
    stage_progress: '阶段进展',
    tool_started: '工具开始',
    tool_completed: '工具完成',
    tool_failed: '工具失败',
    react_turn_started: '正在判断下一步动作',
    react_action_accepted: '动作已通过校验',
    react_action_completed: '动作已完成',
    react_action_blocked: '动作未通过执行门禁',
    react_waiting_for_approval: '工具提案已验证，等待人工审批',
    react_finished: '逐步分析已收敛',
    retry_started: '开始重试',
    recovery_started: '开始恢复',
    answer_delta: '答案更新',
    heartbeat: '仍在运行',
    run_completed: '运行完成',
    run_failed: '运行失败',
    run_cancelled: '运行已取消',
    run_timed_out: '运行超时',
  });

  function boundedText(value, fallback, limit) {
    if (typeof value !== 'string' && typeof value !== 'number') return fallback || '';
    return String(value).replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, limit || 160);
  }

  function boundedAnswerDelta(value) {
    if (typeof value !== 'string') return '';
    return value.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, MAX_ANSWER_DELTA);
  }

  function safeData(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const result = {};
    Object.keys(value).forEach(key => {
      if (!ALLOWED_DATA.has(key)) return;
      const item = value[key];
      if (typeof item === 'boolean') result[key] = item;
      else if (typeof item === 'number' && Number.isFinite(item)) result[key] = item;
      else if (typeof item === 'string') result[key] = boundedText(item, '', 128);
      else if (key === 'recovery_actions' && Array.isArray(item)) {
        result[key] = item.filter(action => typeof action === 'string')
          .map(action => boundedText(action, '', 64)).filter(Boolean).slice(0, 4);
      }
      if (key === 'answer_delta') {
        const delta = boundedAnswerDelta(item);
        if (delta) result[key] = delta;
        else delete result[key];
      }
    });
    return result;
  }

  function normalizeEvent(value, expectedRunId) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    if (value.schema_version !== RUN_EVENT_SCHEMA_VERSION) return null;
    const runId = boundedText(value.run_id, '', 128);
    if (typeof value.sequence === 'boolean' || value.sequence === null || value.sequence === '') return null;
    const sequence = Number(value.sequence);
    const kind = boundedText(value.kind, '', 48);
    const status = boundedText(value.status, '', 48).toUpperCase();
    if (!runId || (expectedRunId && runId !== String(expectedRunId)) || !Number.isInteger(sequence) || sequence < 1 ||
      !EVENT_KINDS.has(kind) || !EVENT_STATUSES.has(status) || !EVENT_PHASES.has(boundedText(value.phase, '', 32))) return null;
    return {
      schema_version: boundedText(value.schema_version, '', 80),
      event_id: boundedText(value.event_id, '', 128),
      sequence,
      run_id: runId,
      created_at: boundedText(value.created_at, '', 64),
      kind,
      phase: boundedText(value.phase, '', 32),
      status,
      message: boundedText(value.message, KIND_LABELS[kind] || '运行状态已更新', 240),
      data: safeData(value.data),
      terminal: value.terminal === true || TERMINAL_KINDS.has(kind) || TERMINAL_STATUSES.has(status),
    };
  }

  function isTerminal(value) {
    return Boolean(value && (value.terminal === true || TERMINAL_KINDS.has(value.kind) || TERMINAL_STATUSES.has(String(value.status || '').toUpperCase())));
  }

  function create(options) {
    const config = options || {};
    const runId = String(config.runId || '');
    const fetchImpl = config.fetchImpl || (typeof global.fetch === 'function' ? global.fetch.bind(global) : null);
    const eventSourceFactory = config.eventSourceFactory || (typeof global.EventSource === 'function' ? url => new global.EventSource(url) : null);
    const pollInterval = Math.max(50, Number(config.pollInterval) || 900);
    const reconnectDelay = Math.max(200, Number(config.reconnectDelay) || 500);
    let lastSequence = Math.max(0, Number(config.after) || 0);
    let source = null;
    let timer = null;
    let controller = null;
    let stopped = false;
    let transport = '';
    let unavailableReported = false;
    let reconnectAttempts = 0;
    let pollFailures = 0;
    let pollingStarted = false;
    let started = false;

    const callback = (name, ...args) => {
      if (typeof config[name] === 'function') config[name](...args);
    };
    const eventsUrl = () => {
      const raw = typeof config.eventsPath === 'function' ? config.eventsPath(lastSequence) : config.eventsPath;
      const url = String(raw || '');
      if (!url) return '';
      return url + (url.includes('?') ? '&' : '?') + 'after=' + encodeURIComponent(String(lastSequence)) + '&limit=100';
    };
    const reportUnavailable = () => {
      if (unavailableReported) return;
      unavailableReported = true;
      callback('onUnavailable', { runId, transport });
    };
    const clearTimer = () => {
      if (timer !== null) {
        global.clearTimeout(timer);
        timer = null;
      }
    };
    const deliver = raw => {
      const event = normalizeEvent(raw, runId);
      if (!event || event.sequence <= lastSequence) return false;
      lastSequence = event.sequence;
      callback('onEvent', event);
      if (isTerminal(event)) {
        callback('onComplete', event);
        stop();
      }
      return true;
    };
    const invalidEvent = transportName => {
      pollFailures += 1;
      callback('onError', { transport: transportName, kind: 'invalid_event' });
      return pollFailures >= 3;
    };
    const parseSse = message => {
      try {
        const raw = JSON.parse(String(message?.data || ''));
        const accepted = deliver(raw);
        if (!accepted && invalidEvent('sse')) {
          source?.close?.();
          source = null;
          startPolling();
        } else if (accepted) pollFailures = 0;
      } catch (_) {
        if (invalidEvent('sse')) {
          source?.close?.();
          source = null;
          startPolling();
        }
      }
    };
    const startPolling = () => {
      if (stopped || pollingStarted) return;
      pollingStarted = true;
      if (!fetchImpl) {
        reportUnavailable();
        stop();
        return;
      }
      transport = 'polling';
      callback('onTransport', { transport });
      const poll = async () => {
        if (stopped) return;
        controller = typeof global.AbortController === 'function' ? new global.AbortController() : null;
        try {
          const response = await fetchImpl(eventsUrl(), {
            headers: { Accept: 'application/json' },
            cache: 'no-store',
            signal: controller?.signal,
          });
          if (response.status === 404 || response.status === 405 || response.status === 501) {
            reportUnavailable();
            stop();
            return;
          }
          if (!response.ok) {
            callback('onError', { transport: 'polling', kind: 'error_response' });
            pollFailures += 1;
            const retryable = response.status === 408 || response.status === 425 ||
              response.status === 429 || response.status >= 500;
            if (!retryable || pollFailures >= 3) {
              reportUnavailable();
              stop();
              return;
            }
            timer = global.setTimeout(poll, Math.min(pollInterval * (2 ** pollFailures), 3000));
            return;
          }
          const body = await response.json();
          if (!body || typeof body !== 'object' || Array.isArray(body) || !Array.isArray(body.events)) throw new Error('invalid events response');
          pollFailures = 0;
          const events = body.events;
          let invalidCount = 0;
          events.forEach(raw => { if (!deliver(raw) && raw && typeof raw === 'object') invalidCount += 1; });
          if (invalidCount && invalidEvent('polling')) {
            reportUnavailable();
            stop();
            return;
          }
          if (stopped) return;
          timer = global.setTimeout(poll, events.length ? 80 : pollInterval);
        } catch (error) {
          if (stopped || error?.name === 'AbortError') return;
          pollFailures += 1;
          callback('onError', { transport: 'polling', kind: 'unavailable' });
          if (pollFailures >= 3) {
            reportUnavailable();
            stop();
            return;
          }
          timer = global.setTimeout(poll, Math.min(pollInterval * (2 ** pollFailures), 3000));
        } finally {
          controller = null;
        }
      };
      poll();
    };
    const startSse = () => {
      if (stopped) return;
      if (!eventSourceFactory) {
        startPolling();
        return;
      }
      transport = 'sse';
      callback('onTransport', { transport });
      try {
        source = eventSourceFactory(eventsUrl());
        source.addEventListener?.('run_event', parseSse);
        source.onmessage = parseSse;
        source.onopen = () => { reconnectAttempts = 0; callback('onOpen', { transport: 'sse', sequence: lastSequence }); };
        source.onerror = () => {
          if (stopped) return;
          source?.close?.();
          source = null;
          callback('onError', { transport: 'sse', kind: 'disconnected' });
          if (reconnectAttempts < 2) {
            reconnectAttempts += 1;
            timer = global.setTimeout(() => { timer = null; startSse(); }, reconnectDelay);
          } else {
            startPolling();
          }
        };
      } catch (_) {
        callback('onError', { transport: 'sse', kind: 'unavailable' });
        startPolling();
      }
    };
    function stop() {
      if (stopped) return;
      stopped = true;
      clearTimer();
      source?.close?.();
      source = null;
      controller?.abort?.();
      controller = null;
      callback('onStop', { transport, sequence: lastSequence });
    }
    return {
      start: () => {
        if (started) return;
        started = true;
        if (!runId || !(typeof config.eventsPath === 'function' || String(config.eventsPath || ''))) {
          reportUnavailable();
          return;
        }
        startSse();
      },
      stop,
      close: stop,
      get lastSequence() { return lastSequence; },
      get transport() { return transport; },
    };
  }

  global.ConsoleRunEvents = Object.freeze({
    create,
    normalize: normalizeEvent,
    isTerminal,
    phaseLabel: phase => PHASE_LABELS[String(phase || '')] || '处理中',
    kindLabel: kind => KIND_LABELS[String(kind || '')] || '运行状态',
    phaseLabels: PHASE_LABELS,
  });
}(window));
