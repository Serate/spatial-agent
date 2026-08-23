/* Schema-driven, domain-neutral Action form and invocation host. */
(function attachConsoleActionHost(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleActionHost = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.console-action-host.v1";
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const record = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);

  function mount(options = {}) {
    const target = options.target;
    if (!target) throw new TypeError("ActionHost target is required");
    const catalog = record(options.catalog) ? options.catalog : {};
    const actions = (Array.isArray(catalog.actions) ? catalog.actions : []).filter(item => record(item) && item.id).slice(0, 32);
    const initialValues = record(options.initialValues) ? options.initialValues : {};
    const invoke = typeof options.invoke === "function" ? options.invoke : async () => { throw new Error("动作执行入口不可用"); };
    const onResult = typeof options.onResult === "function" ? options.onResult : () => {};
    if (!actions.length) {
      target.innerHTML = '<div class="distribution-note">当前领域没有声明可执行动作。</div>';
      return Object.freeze({schema_version: SCHEMA_VERSION, action_count: 0});
    }
    target.innerHTML = '<div class="action-host-head"><label for="domainActionSelect">动作</label><select id="domainActionSelect">'
      + actions.map(item => '<option value="' + escapeHtml(item.id) + '">' + escapeHtml(item.label || item.id) + '</option>').join("")
      + '</select></div><div id="domainActionDescription" class="distribution-note"></div><div id="domainActionFields" class="action-host-fields"></div>'
      + '<button id="domainActionExecute" type="button">执行动作</button><div id="domainActionStatus" class="distribution-note" aria-live="polite"></div>';
    const select = target.querySelector("#domainActionSelect");
    const fields = target.querySelector("#domainActionFields");
    const description = target.querySelector("#domainActionDescription");
    const button = target.querySelector("#domainActionExecute");
    const status = target.querySelector("#domainActionStatus");
    const selectedSpec = () => actions.find(item => item.id === select.value) || actions[0];

    function renderFields() {
      const action = selectedSpec();
      const schema = record(action.input_schema) ? action.input_schema : {};
      const properties = record(schema.properties) ? schema.properties : {};
      const required = new Set(Array.isArray(schema.required) ? schema.required : []);
      description.textContent = action.description || "该动作由当前领域声明。";
      fields.innerHTML = Object.entries(properties).slice(0, 24).map(([name, spec], index) => renderField(name, spec, required.has(name), initialValues, index)).join("")
        || '<div class="distribution-note">该动作不需要输入参数。</div>';
      status.textContent = "";
    }

    select.addEventListener("change", renderFields);
    button.addEventListener("click", async () => {
      const action = selectedSpec();
      button.disabled = true;
      status.textContent = "正在执行动作…";
      try {
        const payload = collectPayload(fields, action.input_schema || {});
        const result = await invoke(action.id, payload);
        status.textContent = "动作已完成，结果已进入统一工作区。";
        await onResult(result, action);
      } catch (error) {
        status.innerHTML = '<span class="error">' + escapeHtml(error?.message || "动作执行失败") + '</span>';
      } finally {
        button.disabled = false;
      }
    });
    renderFields();
    return Object.freeze({schema_version: SCHEMA_VERSION, action_count: actions.length});
  }

  function renderField(name, rawSpec, required, initialValues, index) {
    const spec = record(rawSpec) ? rawSpec : {};
    const type = String(spec.type || "string");
    const id = "domain-action-field-" + index;
    const label = escapeHtml(spec.title || name) + (required ? " · 必填" : "");
    const description = spec.description ? '<small>' + escapeHtml(spec.description) + '</small>' : "";
    const initial = Object.prototype.hasOwnProperty.call(initialValues, name) ? initialValues[name] : spec.default;
    const data = ' data-action-field="' + escapeHtml(name) + '" data-action-type="' + escapeHtml(type) + '"' + (required ? ' data-required="true"' : "");
    let control;
    if (Array.isArray(spec.enum) && spec.enum.length) {
      control = '<select id="' + id + '"' + data + '><option value="">请选择</option>' + spec.enum.slice(0, 24).map(value => '<option value="' + escapeHtml(value) + '"' + (String(value) === String(initial ?? "") ? " selected" : "") + '>' + escapeHtml(value) + '</option>').join("") + '</select>';
    } else if (type === "boolean") {
      control = '<input id="' + id + '" type="checkbox"' + data + (initial === true ? " checked" : "") + '>';
    } else if (type === "object" || (type === "string" && Number(spec.maxLength || 0) > 500)) {
      const value = type === "object" && initial !== undefined ? JSON.stringify(initial, null, 2) : String(initial ?? "");
      control = '<textarea id="' + id + '"' + data + ' placeholder="' + (type === "object" ? "{}" : "请输入内容") + '">' + escapeHtml(value) + '</textarea>';
    } else {
      const value = Array.isArray(initial) ? initial.join(", ") : String(initial ?? "");
      const inputType = ["number", "integer"].includes(type) ? "number" : "text";
      const itemType = type === "array" ? String(spec.items?.type || "string") : "";
      control = '<input id="' + id + '" type="' + inputType + '"' + data + (itemType ? ' data-item-type="' + escapeHtml(itemType) + '"' : "")
        + (spec.minimum !== undefined ? ' min="' + escapeHtml(spec.minimum) + '"' : "") + (spec.maximum !== undefined ? ' max="' + escapeHtml(spec.maximum) + '"' : "")
        + (["number", "integer"].includes(type) ? ' step="' + (type === "integer" ? "1" : "any") + '"' : "") + ' value="' + escapeHtml(value) + '">';
    }
    return '<div class="workflow-field action-host-field"><label for="' + id + '">' + label + '</label>' + control + description + '</div>';
  }

  function collectPayload(container, rawSchema) {
    const schema = record(rawSchema) ? rawSchema : {};
    const properties = record(schema.properties) ? schema.properties : {};
    const required = new Set(Array.isArray(schema.required) ? schema.required : []);
    const payload = {};
    container.querySelectorAll("[data-action-field]").forEach(field => {
      const name = field.dataset.actionField;
      const spec = record(properties[name]) ? properties[name] : {};
      const type = field.dataset.actionType || "string";
      let value = type === "boolean" ? field.checked : field.value.trim();
      if (type !== "boolean" && value === "") {
        if (required.has(name)) throw new Error((spec.title || name) + "不能为空");
        return;
      }
      if (["number", "integer"].includes(type)) {
        value = Number(value);
        if (!Number.isFinite(value) || (type === "integer" && !Number.isInteger(value))) throw new Error((spec.title || name) + "必须是有效数字");
        if (spec.minimum !== undefined && value < Number(spec.minimum)) throw new Error((spec.title || name) + "不能小于 " + spec.minimum);
        if (spec.maximum !== undefined && value > Number(spec.maximum)) throw new Error((spec.title || name) + "不能大于 " + spec.maximum);
      } else if (type === "array") {
        value = String(value).split(/[,，\n]+/).map(item => item.trim()).filter(Boolean);
        if (field.dataset.itemType === "number") {
          value = value.map(Number);
          if (value.some(item => !Number.isFinite(item))) throw new Error((spec.title || name) + "包含无效数字");
        }
        if (spec.minItems !== undefined && value.length < Number(spec.minItems)) throw new Error((spec.title || name) + "至少需要 " + spec.minItems + " 项");
        if (spec.maxItems !== undefined && value.length > Number(spec.maxItems)) throw new Error((spec.title || name) + "最多允许 " + spec.maxItems + " 项");
      } else if (type === "object") {
        try { value = JSON.parse(value); } catch (_) { throw new Error((spec.title || name) + "必须是有效 JSON"); }
        if (!record(value)) throw new Error((spec.title || name) + "必须是 JSON 对象");
      } else {
        if (spec.minLength !== undefined && value.length < Number(spec.minLength)) throw new Error((spec.title || name) + "长度不足");
        if (spec.maxLength !== undefined && value.length > Number(spec.maxLength)) throw new Error((spec.title || name) + "长度超限");
      }
      payload[name] = value;
    });
    return payload;
  }

  return Object.freeze({SCHEMA_VERSION, mount, collectPayload});
});
