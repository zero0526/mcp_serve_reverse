(() => {
  if (window.__api_lineage_runtime_hooked__) return;
  window.__api_lineage_runtime_hooked__ = true;

  function emitBridgeEvent(eventType, payload, stack) {
    if (typeof window.__api_lineage_emit__ === "function") {
      window.__api_lineage_emit__(eventType, payload, stack);
      return;
    }
    try {
      if (typeof window.__api_lineage_bridge__ === "function") {
        window.__api_lineage_bridge__(
          JSON.stringify({
            event_type: eventType,
            timestamp_ms: Date.now(),
            stack: stack || null,
            payload: payload,
          })
        );
      }
    } catch (e) {}
  }

  window.addEventListener("error", (event) => {
    emitBridgeEvent(
      "runtime_error",
      {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      },
      event.error ? event.error.stack : null
    );
  });

  window.addEventListener("unhandledrejection", (event) => {
    emitBridgeEvent(
      "runtime_error",
      {
        type: "unhandledrejection",
        reason: String(event.reason),
      },
      event.reason && event.reason.stack ? event.reason.stack : null
    );
  });
})();
