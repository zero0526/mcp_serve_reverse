(() => {
  if (window.__api_lineage_serializer_hooked__) return;
  window.__api_lineage_serializer_hooked__ = true;

  const originalStringify = JSON.stringify;
  const originalParse = JSON.parse;

  function emitBridgeEvent(eventType, payload, stack) {
    if (typeof window.__api_lineage_emit__ === "function") {
      window.__api_lineage_emit__(eventType, payload, stack);
      return;
    }
    try {
      if (typeof window.__api_lineage_bridge__ === "function") {
        window.__api_lineage_bridge__(
          originalStringify({
            event_type: eventType,
            timestamp_ms: Date.now(),
            stack: stack || null,
            payload: payload,
          })
        );
      }
    } catch (e) {}
  }

  let inStringifyHook = false;
  JSON.stringify = function (value, replacer, space) {
    const result = originalStringify.apply(this, arguments);
    if (!inStringifyHook && typeof result === "string" && result.length > 5) {
      inStringifyHook = true;
      try {
        const stack = new Error().stack;
        emitBridgeEvent(
          "serialize",
          {
            operation: "json_stringify",
            output_preview: result.slice(0, 1024),
            output_length: result.length,
          },
          stack
        );
      } catch (e) {
      } finally {
        inStringifyHook = false;
      }
    }
    return result;
  };

  let inParseHook = false;
  JSON.parse = function (text, reviver) {
    const result = originalParse.apply(this, arguments);
    if (!inParseHook && typeof text === "string" && text.length > 5) {
      inParseHook = true;
      try {
        const stack = new Error().stack;
        emitBridgeEvent(
          "deserialize",
          {
            operation: "json_parse",
            input_preview: text.slice(0, 1024),
            input_length: text.length,
          },
          stack
        );
      } catch (e) {
      } finally {
        inParseHook = false;
      }
    }
    return result;
  };
})();
