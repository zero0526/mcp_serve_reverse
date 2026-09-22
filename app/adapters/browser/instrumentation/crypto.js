(() => {
  if (window.__api_lineage_crypto_hooked__) return;
  window.__api_lineage_crypto_hooked__ = true;

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

  // 1. Hook Web Crypto API
  if (typeof window.crypto !== "undefined" && window.crypto.subtle) {
    const subtle = window.crypto.subtle;

    if (typeof subtle.digest === "function") {
      const originalDigest = subtle.digest;
      subtle.digest = async function (algorithm, data) {
        const stack = new Error().stack;
        const algoName =
          typeof algorithm === "string" ? algorithm : algorithm?.name || "UNKNOWN";

        const result = await originalDigest.apply(this, arguments);

        // Chuyển kết quả sang hex preview
        let outputHex = "";
        try {
          const arr = new Uint8Array(result);
          outputHex = Array.from(arr)
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("");
        } catch (e) {}

        emitBridgeEvent(
          "crypto_operation",
          {
            operation: "digest",
            algorithm: algoName,
            byte_length: data?.byteLength || 0,
            output_hex: outputHex.slice(0, 128),
          },
          stack
        );

        return result;
      };
    }

    if (typeof subtle.sign === "function") {
      const originalSign = subtle.sign;
      subtle.sign = async function (algorithm, key, data) {
        const stack = new Error().stack;
        const algoName =
          typeof algorithm === "string" ? algorithm : algorithm?.name || "UNKNOWN";

        const result = await originalSign.apply(this, arguments);

        emitBridgeEvent(
          "crypto_operation",
          {
            operation: "sign",
            algorithm: algoName,
            byte_length: data?.byteLength || 0,
          },
          stack
        );

        return result;
      };
    }
  }

  // 2. Hook JSON.stringify để theo dõi các thao tác serialize payload
  const originalStringify = JSON.stringify;
  JSON.stringify = function (value, replacer, space) {
    const stack = new Error().stack;

    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      stack &&
      !stack.includes("api_lineage")
    ) {
      try {
        const keys = Object.keys(value);
        if (keys.length > 0 && keys.length < 50) {
          emitBridgeEvent(
            "serialize",
            {
              format: "json",
              keys: keys,
            },
            stack
          );
        }
      } catch (e) {}
    }

    return originalStringify.apply(this, arguments);
  };
})();
