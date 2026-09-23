(() => {
  if (window.__api_lineage_fetch_hooked__) return;
  window.__api_lineage_fetch_hooked__ = true;

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

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const stack = new Error().stack;
    let resource = args[0];
    let config = args[1] || {};

    let url = "";
    let method = "GET";
    let headers = {};
    let body = null;

    if (typeof resource === "string") {
      url = resource;
    } else if (resource instanceof Request) {
      url = resource.url;
      method = resource.method;
    }

    if (config.method) method = config.method.toUpperCase();
    if (config.headers) {
      if (config.headers instanceof Headers) {
        config.headers.forEach((v, k) => {
          headers[k] = v;
        });
      } else if (Array.isArray(config.headers)) {
        config.headers.forEach(([k, v]) => {
          headers[k] = v;
        });
      } else if (typeof config.headers === "object") {
        headers = { ...config.headers };
      }
    }
    if (config.body !== undefined && config.body !== null) {
      if (typeof config.body === "string") {
        body = config.body;
      } else {
        try {
          body = String(config.body);
        } catch (e) {
          body = "[Non-string body]";
        }
      }
    }

    const requestId = "fetch_" + Math.random().toString(36).substring(2, 11);

    // Build options with x-lineage-req-id header attached
    const fetchOptions = { ...config };
    try {
      if (fetchOptions.headers instanceof Headers) {
        fetchOptions.headers.set("x-lineage-req-id", requestId);
      } else if (Array.isArray(fetchOptions.headers)) {
        fetchOptions.headers = [...fetchOptions.headers, ["x-lineage-req-id", requestId]];
      } else if (fetchOptions.headers && typeof fetchOptions.headers === "object") {
        fetchOptions.headers = { ...fetchOptions.headers, "x-lineage-req-id": requestId };
      } else {
        fetchOptions.headers = { "x-lineage-req-id": requestId };
      }

      if (resource instanceof Request) {
        resource.headers.set("x-lineage-req-id", requestId);
      }
      headers["x-lineage-req-id"] = requestId;
    } catch (e) {}

    emitBridgeEvent(
      "network_request",
      {
        transport: "fetch",
        request_id: requestId,
        url: url,
        method: method,
        headers: headers,
        body: body,
      },
      stack
    );

    try {
      const response = await originalFetch.apply(this, [resource, fetchOptions]);
      response.__api_lineage_req_id__ = requestId;

      // Clone response to inspect body without consuming the stream
      try {
        const clone = response.clone();
        clone.__api_lineage_internal_clone__ = true;
        clone
          .text()
          .then((text) => {
            const respHeaders = {};
            clone.headers.forEach((v, k) => {
              respHeaders[k] = v;
            });

            emitBridgeEvent(
              "network_response",
              {
                transport: "fetch",
                request_id: requestId,
                url: url,
                status_code: clone.status,
                headers: respHeaders,
                body: text.slice(0, 65536),
                body_size: text.length,
              },
              null
            );
          })
          .catch(() => {});
      } catch (cloneErr) {}

      return response;
    } catch (err) {
      emitBridgeEvent(
        "network_failed",
        {
          transport: "fetch",
          request_id: requestId,
          url: url,
          error_message: String(err),
        },
        stack
      );
      throw err;
    }
  };

  function wrapWithLineageProxy(target, requestId, originStack) {
    if (target === null || typeof target !== "object") return target;

    try {
      return new Proxy(target, {
        get(obj, prop, receiver) {
          if (typeof prop === "symbol" || prop === "toJSON" || prop === "then") {
            return Reflect.get(obj, prop, receiver);
          }

          const accessStack = new Error().stack;
          const val = obj[prop];

          emitBridgeEvent(
            "response_field_read",
            {
              request_id: requestId,
              field: String(prop),
              value_preview: val !== undefined && val !== null ? String(val).slice(0, 256) : null,
            },
            accessStack
          );

          if (val !== null && typeof val === "object") {
            return wrapWithLineageProxy(val, requestId, originStack);
          }
          return val;
        },
      });
    } catch (e) {
      return target;
    }
  }

  // Hook Response prototype methods to capture consumer functions
  if (typeof Response !== "undefined" && Response.prototype) {
    const originalJson = Response.prototype.json;
    const originalText = Response.prototype.text;

    Response.prototype.json = async function () {
      const handlerStack = new Error().stack;
      const requestId = this.__api_lineage_req_id__ || "unknown_req";

      const data = await originalJson.apply(this, arguments);

      emitBridgeEvent(
        "response_consumed",
        {
          request_id: requestId,
          format: "json",
          data_keys: data && typeof data === "object" ? Object.keys(data) : [],
        },
        handlerStack
      );

      return wrapWithLineageProxy(data, requestId, handlerStack);
    };

    Response.prototype.text = async function () {
      const handlerStack = new Error().stack;
      const requestId = this.__api_lineage_req_id__ || "unknown_req";

      const text = await originalText.apply(this, arguments);

      if (!this.__api_lineage_internal_clone__) {
        emitBridgeEvent(
          "response_consumed",
          {
            request_id: requestId,
            format: "text",
            length: text ? text.length : 0,
          },
          handlerStack
        );
      }

      return text;
    };
  }
})();
