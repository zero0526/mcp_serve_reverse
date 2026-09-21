(() => {
  if (window.__api_lineage_storage_hooked__) return;
  window.__api_lineage_storage_hooked__ = true;

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

  // Pre-seed storage if config exists on window
  window.__api_lineage_apply_preseed__ = function (storageSeed) {
    if (!storageSeed) return;
    try {
      if (storageSeed.local_storage) {
        for (const [k, v] of Object.entries(storageSeed.local_storage)) {
          window.localStorage.setItem(k, v);
        }
      }
      if (storageSeed.session_storage) {
        for (const [k, v] of Object.entries(storageSeed.session_storage)) {
          window.sessionStorage.setItem(k, v);
        }
      }
    } catch (e) {}
  };

  const originalLocalSet = Storage.prototype.setItem;
  const originalLocalGet = Storage.prototype.getItem;
  const originalLocalRemove = Storage.prototype.removeItem;
  const originalLocalClear = Storage.prototype.clear;

  Storage.prototype.setItem = function (key, value) {
    const stack = new Error().stack;
    const isLocal = this === window.localStorage;
    const storageType = isLocal ? "local_storage" : "session_storage";

    emitBridgeEvent(
      "storage_write",
      {
        storage_type: storageType,
        operation: "write",
        storage_key: String(key),
        value_preview: String(value).slice(0, 1024),
        value_length: String(value).length,
      },
      stack
    );

    return originalLocalSet.apply(this, arguments);
  };

  Storage.prototype.getItem = function (key) {
    const result = originalLocalGet.apply(this, arguments);
    const stack = new Error().stack;
    const isLocal = this === window.localStorage;
    const storageType = isLocal ? "local_storage" : "session_storage";

    emitBridgeEvent(
      "storage_read",
      {
        storage_type: storageType,
        operation: "read",
        storage_key: String(key),
        value_preview: result !== null ? String(result).slice(0, 1024) : null,
        value_length: result !== null ? String(result).length : 0,
        found: result !== null,
      },
      stack
    );

    return result;
  };

  Storage.prototype.removeItem = function (key) {
    const stack = new Error().stack;
    const isLocal = this === window.localStorage;
    const storageType = isLocal ? "local_storage" : "session_storage";

    emitBridgeEvent(
      "storage_delete",
      {
        storage_type: storageType,
        operation: "delete",
        storage_key: String(key),
      },
      stack
    );

    return originalLocalRemove.apply(this, arguments);
  };

  Storage.prototype.clear = function () {
    const stack = new Error().stack;
    const isLocal = this === window.localStorage;
    const storageType = isLocal ? "local_storage" : "session_storage";

    emitBridgeEvent(
      "storage_clear",
      {
        storage_type: storageType,
        operation: "clear",
      },
      stack
    );

    return originalLocalClear.apply(this, arguments);
  };
})();
