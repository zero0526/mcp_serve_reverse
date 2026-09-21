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
    const [resource, config] = args;

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

    if (config) {
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
    }

    const requestId = "fetch_" + Math.random().toString(36).substring(2, 11);

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
      const response = await originalFetch.apply(this, args);

      // Clone response to inspect body without consuming the stream
      try {
        const clone = response.clone();
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
                body: text.slice(0, 4096),
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
})();
