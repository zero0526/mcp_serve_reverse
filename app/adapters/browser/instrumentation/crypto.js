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

  // 1. Hook Web Crypto API (SubtleCrypto & getRandomValues)
  if (typeof window.crypto !== "undefined") {
    // A. crypto.getRandomValues (bắt sinh Nonce, Salt, IV, Key)
    if (typeof window.crypto.getRandomValues === "function") {
      const origGetRandomValues = window.crypto.getRandomValues.bind(window.crypto);
      window.crypto.getRandomValues = function (array) {
        const result = origGetRandomValues(array);
        try {
          const stack = new Error().stack;
          if (stack && !stack.includes("api_lineage")) {
            let hexPreview = "";
            if (array && array.byteLength) {
              const u8 = new Uint8Array(array.buffer, array.byteOffset, Math.min(array.byteLength, 32));
              hexPreview = Array.from(u8).map((b) => b.toString(16).padStart(2, "0")).join("");
            }
            emitBridgeEvent(
              "crypto_operation",
              {
                operation: "getRandomValues",
                algorithm: "CSPRNG",
                byte_length: array?.byteLength || 0,
                output_hex: hexPreview,
              },
              stack
            );
          }
        } catch (e) {}
        return result;
      };
    }

    // B. SubtleCrypto (digest, sign, encrypt, decrypt)
    if (window.crypto.subtle) {
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
  }

  // 2. Hook Encoding Primitives (TextEncoder / TextDecoder & btoa / atob)
  if (typeof window.TextEncoder !== "undefined") {
    const origEncode = TextEncoder.prototype.encode;
    TextEncoder.prototype.encode = function (input) {
      const result = origEncode.apply(this, arguments);
      try {
        const stack = new Error().stack;
        if (stack && !stack.includes("api_lineage") && typeof input === "string" && input.length > 2) {
          emitBridgeEvent(
            "serialize",
            {
              format: "utf8_encode",
              input_preview: input.length > 100 ? input.slice(0, 100) + "..." : input,
              byte_length: result.byteLength,
            },
            stack
          );
        }
      } catch (e) {}
      return result;
    };
  }

  if (typeof window.btoa === "function") {
    const origBtoa = window.btoa;
    window.btoa = function (data) {
      const result = origBtoa.apply(this, arguments);
      try {
        const stack = new Error().stack;
        if (stack && !stack.includes("api_lineage")) {
          emitBridgeEvent(
            "function_call",
            {
              function_name: "btoa",
              arguments: [typeof data === "string" && data.length > 80 ? data.slice(0, 80) + "..." : data],
              return_value: typeof result === "string" && result.length > 80 ? result.slice(0, 80) + "..." : result,
            },
            stack
          );
        }
      } catch (e) {}
      return result;
    };
  }

  if (typeof window.atob === "function") {
    const origAtob = window.atob;
    window.atob = function (data) {
      const result = origAtob.apply(this, arguments);
      try {
        const stack = new Error().stack;
        if (stack && !stack.includes("api_lineage")) {
          emitBridgeEvent(
            "function_call",
            {
              function_name: "atob",
              arguments: [typeof data === "string" && data.length > 80 ? data.slice(0, 80) + "..." : data],
              return_value: typeof result === "string" && result.length > 80 ? result.slice(0, 80) + "..." : result,
            },
            stack
          );
        }
      } catch (e) {}
      return result;
    };
  }

  // 3. Hook WebAssembly (WASM module instantiation & exported crypto functions)
  if (typeof window.WebAssembly !== "undefined") {
    if (typeof WebAssembly.instantiate === "function") {
      const origInstantiate = WebAssembly.instantiate;
      WebAssembly.instantiate = async function (bufferSource, importObject) {
        const stack = new Error().stack;
        try {
          const byteLen = bufferSource?.byteLength || bufferSource?.length || 0;
          emitBridgeEvent(
            "crypto_operation",
            {
              operation: "wasm_instantiate",
              algorithm: "WebAssembly",
              byte_length: byteLen,
            },
            stack
          );
        } catch (e) {}
        return origInstantiate.apply(this, arguments);
      };
    }
  }

  // 4. Hook Web Workers (lắng nghe luồng dữ liệu tính toán chạy ngầm)
  if (typeof window.Worker === "function") {
    const OrigWorker = window.Worker;
    window.Worker = function (scriptURL, options) {
      const worker = new OrigWorker(scriptURL, options);
      try {
        const stack = new Error().stack;
        emitBridgeEvent(
          "function_call",
          {
            function_name: "new Worker",
            arguments: [String(scriptURL)],
          },
          stack
        );

        const origPostMessage = worker.postMessage.bind(worker);
        worker.postMessage = function (message, transfer) {
          try {
            const wStack = new Error().stack;
            if (wStack && !wStack.includes("api_lineage")) {
              emitBridgeEvent(
                "function_call",
                {
                  function_name: "Worker.postMessage",
                  payload_preview: typeof message === "object" ? JSON.stringify(message).slice(0, 100) : String(message),
                },
                wStack
              );
            }
          } catch (e) {}
          return origPostMessage(message, transfer);
        };
      } catch (e) {}
      return worker;
    };
  }

  // 5. Hook JSON.stringify để theo dõi các thao tác serialize payload
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
