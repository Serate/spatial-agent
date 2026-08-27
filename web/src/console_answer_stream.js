(() => {
  "use strict";

  const DEFAULT_MAX_LENGTH = 1800;
  const DEFAULT_INTERVAL = 24;

  function asCharacters(value) {
    return Array.from(String(value ?? ""));
  }

  function clamp(value, maxLength) {
    return asCharacters(value).slice(0, maxLength).join("");
  }

  function create(options = {}) {
    const onText = typeof options.onText === "function" ? options.onText : () => {};
    const maxLength = Number.isFinite(options.maxLength) && options.maxLength > 0
      ? Math.floor(options.maxLength)
      : DEFAULT_MAX_LENGTH;
    const schedule = typeof options.schedule === "function"
      ? options.schedule
      : callback => {
        if (typeof window.requestAnimationFrame === "function") return window.requestAnimationFrame(callback);
        return window.setTimeout(callback, DEFAULT_INTERVAL);
      };
    const cancelSchedule = typeof options.cancelSchedule === "function"
      ? options.cancelSchedule
      : handle => {
        if (typeof window.cancelAnimationFrame === "function") window.cancelAnimationFrame(handle);
        else window.clearTimeout(handle);
      };

    let target = "";
    let rendered = "";
    let scheduled = null;
    let waiters = [];

    function settle() {
      if (rendered !== target || !waiters.length) return;
      const pending = waiters;
      waiters = [];
      pending.forEach(resolve => resolve(rendered));
    }

    function tick() {
      scheduled = null;
      const renderedCharacters = asCharacters(rendered);
      const targetCharacters = asCharacters(target);
      if (renderedCharacters.length < targetCharacters.length) {
        rendered = targetCharacters.slice(0, renderedCharacters.length + 1).join("");
        onText(rendered);
      }
      if (rendered !== target) {
        scheduled = schedule(tick);
      } else {
        settle();
      }
    }

    function ensureScheduled() {
      if (scheduled === null && rendered !== target) scheduled = schedule(tick);
    }

    return {
      push(value) {
        target = clamp(target + String(value ?? ""), maxLength);
        ensureScheduled();
      },

      finish(value) {
        if (typeof value === "string") {
          const next = clamp(value, maxLength);
          if (!next.startsWith(rendered)) {
            const currentCharacters = asCharacters(rendered);
            const nextCharacters = asCharacters(next);
            let commonLength = 0;
            while (commonLength < currentCharacters.length
              && commonLength < nextCharacters.length
              && currentCharacters[commonLength] === nextCharacters[commonLength]) {
              commonLength += 1;
            }
            rendered = nextCharacters.slice(0, commonLength).join("");
            onText(rendered);
          }
          target = next;
        }
        ensureScheduled();
        if (rendered === target) return Promise.resolve(rendered);
        return new Promise(resolve => {
          waiters.push(resolve);
          ensureScheduled();
        });
      },

      reset() {
        if (scheduled !== null) cancelSchedule(scheduled);
        scheduled = null;
        target = "";
        rendered = "";
        waiters.forEach(resolve => resolve(rendered));
        waiters = [];
      },

      flush() {
        if (scheduled !== null) cancelSchedule(scheduled);
        scheduled = null;
        rendered = target;
        onText(rendered);
        settle();
        return rendered;
      },

      getText() { return target; },
      getRenderedText() { return rendered; },
    };
  }

  window.ConsoleAnswerStream = Object.freeze({create});
})();
