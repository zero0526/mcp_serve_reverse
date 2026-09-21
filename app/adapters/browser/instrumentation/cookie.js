(() => {
  if (window.__api_lineage_cookie_hooked__) return;
  window.__api_lineage_cookie_hooked__ = true;

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

  let cookieDescriptor =
    Object.getOwnPropertyDescriptor(Document.prototype, "cookie") ||
    Object.getOwnPropertyDescriptor(HTMLDocument.prototype, "cookie");

  if (cookieDescriptor && cookieDescriptor.set && cookieDescriptor.get) {
    const originalGet = cookieDescriptor.get;
    const originalSet = cookieDescriptor.set;

    Object.defineProperty(document, "cookie", {
      get: function () {
        const val = originalGet.apply(this);
        emitBridgeEvent("storage_read", {
          storage_type: "cookie",
          operation: "read",
          cookie_string_preview: (val || "").slice(0, 512),
        });
        return val;
      },
      set: function (val) {
        const stack = new Error().stack;
        const cookieStr = String(val);
        const name = cookieStr.split("=")[0].trim();

        emitBridgeEvent(
          "storage_write",
          {
            storage_type: "cookie",
            operation: "write",
            storage_key: name,
            raw_cookie_preview: cookieStr.slice(0, 512),
          },
          stack
        );

        return originalSet.apply(this, arguments);
      },
      configurable: true,
      enumerable: true,
    });
  }
})();
