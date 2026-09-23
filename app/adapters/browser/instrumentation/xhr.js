(() => {
  if (window.__api_lineage_xhr_hooked__) return;
  window.__api_lineage_xhr_hooked__ = true;

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

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__api_lineage_info__ = {
      id: "xhr_" + Math.random().toString(36).substring(2, 11),
      method: (method || "GET").toUpperCase(),
      url: String(url),
      headers: {},
      body: null,
    };
    return originalOpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.setRequestHeader = function (header, value) {
    if (this.__api_lineage_info__) {
      this.__api_lineage_info__.headers[header] = value;
    }
    return originalSetRequestHeader.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function (body) {
    const stack = new Error().stack;
    const info = this.__api_lineage_info__ || {
      id: "xhr_" + Math.random().toString(36).substring(2, 11),
      method: "UNKNOWN",
      url: "",
      headers: {},
    };

    if (body !== undefined && body !== null) {
      info.body = typeof body === "string" ? body : String(body);
    }

    try {
      this.setRequestHeader("x-lineage-req-id", info.id);
      info.headers["x-lineage-req-id"] = info.id;
    } catch (e) {}

    emitBridgeEvent(
      "network_request",
      {
        transport: "xhr",
        request_id: info.id,
        url: info.url,
        method: info.method,
        headers: info.headers,
        body: info.body,
      },
      stack
    );

    this.addEventListener("load", () => {
      let respBody = "";
      try {
        if (typeof this.responseText === "string") {
          respBody = this.responseText.slice(0, 65536);
        }
      } catch (e) {}

      emitBridgeEvent(
        "network_response",
        {
          transport: "xhr",
          request_id: info.id,
          url: info.url,
          status_code: this.status,
          body: respBody,
          body_size: respBody.length,
        },
        null
      );
    });

    this.addEventListener("error", () => {
      emitBridgeEvent(
        "network_failed",
        {
          transport: "xhr",
          request_id: info.id,
          url: info.url,
          status_code: this.status,
        },
        null
      );
    });

    return originalSend.apply(this, arguments);
  };
})();
