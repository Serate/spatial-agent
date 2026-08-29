/* Safe, domain-neutral projection for human tool approvals. */
(function attachConsoleToolApprovals(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleToolApprovals = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.tool-approval-visibility.v1";
  const MAX_ITEMS = 32;
  const STATUS_LABELS = Object.freeze({
    pending: "待审批", approved: "已批准", rejected: "已拒绝",
    expired: "已过期", revoked: "已撤销", invalid: "无效",
  });
  const RECOVERY_LABELS = Object.freeze({
    bound: "已恢复并绑定", degraded: "等待运行时恢复", not_loaded: "运行时尚未加载",
  });
  const ACTION_LABELS = Object.freeze({approve: "批准", reject: "拒绝", revoke: "撤销"});
  const record = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const text = (value, fallback = "", limit = 160) => {
    if (typeof value !== "string" && typeof value !== "number") return fallback;
    const result = String(value).replace(/[\u0000-\u001f\u007f]/g, " ").trim();
    return (result || fallback).slice(0, limit);
  };

  function normalize(payload) {
    const source = record(payload) ? payload : {};
    const raw = Array.isArray(source.visibility) ? source.visibility : [];
    return {
      schema_version: SCHEMA_VERSION,
      domain_id: text(source.domain_id, "unknown", 80),
      items: raw.slice(0, MAX_ITEMS).map(item => {
        if (!record(item) || item.schema_version !== SCHEMA_VERSION) return null;
        const status = Object.prototype.hasOwnProperty.call(STATUS_LABELS, item.status)
          ? item.status : "invalid";
        const recovery = record(item.recovery) ? item.recovery : {};
        const recoveryState = Object.prototype.hasOwnProperty.call(RECOVERY_LABELS, recovery.state)
          ? recovery.state : "not_loaded";
        return {
          approval_id: text(item.approval_id, "unknown", 96),
          name: text(item.name, "未命名工具", 96),
          domain_id: text(item.domain_id, "unknown", 80),
          status,
          version: Number.isInteger(item.version) ? Math.max(0, item.version) : 0,
          receipt_fingerprint: text(item.receipt_fingerprint, "", 128),
          reason_code: text(item.reason_code, "", 96),
          allowed_actions: Array.isArray(item.allowed_actions)
            ? item.allowed_actions.filter(action => ACTION_LABELS[action]).slice(0, 4) : [],
          recovery: {
            state: recoveryState,
            reason_code: text(recovery.reason_code, "", 96),
          },
        };
      }).filter(Boolean),
    };
  }

  function mount(options = {}) {
    const target = options.target;
    if (!target) throw new TypeError("approval target is required");
    const escapeHtml = typeof options.escapeHtml === "function"
      ? options.escapeHtml : value => text(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      })[char]);
    const model = normalize(options.payload);
    if (!model.items.length) {
      target.innerHTML = '<div class="tool-governance-empty">当前没有需要处理的工具提案。</div>';
      return model;
    }
    target.innerHTML = '<div class="tool-governance-list">' + model.items.map((item, index) => {
      const actions = item.allowed_actions.map(action => '<button type="button" class="tool-approval-action '
        + (action === "approve" ? "primary" : "secondary") + '" data-approval-index="'
        + index + '" data-approval-action="' + escapeHtml(action) + '">' + ACTION_LABELS[action] + '</button>').join("");
      const recovery = RECOVERY_LABELS[item.recovery.state];
      return '<article class="tool-approval-item" data-approval-state="' + escapeHtml(item.status)
        + '"><div class="tool-approval-head"><strong>' + escapeHtml(item.name) + '</strong><span class="tool-approval-status '
        + escapeHtml(item.status) + '">' + STATUS_LABELS[item.status] + '</span></div><div class="tool-approval-meta">'
        + escapeHtml(recovery) + ' · 版本 ' + escapeHtml(item.version) + (item.reason_code ? ' · ' + escapeHtml(item.reason_code) : '')
        + '</div>' + (actions ? '<div class="tool-approval-actions">' + actions + '</div>' : '')
        + '<div class="tool-approval-feedback" aria-live="polite"></div></article>';
    }).join("") + '</div>';
    target.querySelectorAll("[data-approval-index]").forEach(button => {
      button.addEventListener("click", async () => {
        const item = model.items[Number(button.dataset.approvalIndex)];
        if (!item || typeof options.onAction !== "function") return;
        const card = button.closest(".tool-approval-item");
        const feedback = card?.querySelector(".tool-approval-feedback");
        button.disabled = true;
        if (feedback) feedback.textContent = "正在提交审批动作…";
        try {
          await options.onAction(item, button.dataset.approvalAction);
        } catch (error) {
          if (feedback) feedback.textContent = text(error?.message, "审批动作失败", 240);
          button.disabled = false;
        }
      });
    });
    return model;
  }

  return Object.freeze({SCHEMA_VERSION, normalize, mount, statusLabels: STATUS_LABELS});
});
