"use strict";

(() => {
  const root = document.querySelector("[data-chat-root]");
  if (!root || root.dataset.liveEnabled !== "true") {
    return;
  }

  const mode = root.dataset.chatMode;
  const conversationId = root.dataset.conversationId;
  const csrfToken = root.dataset.chatCsrf;
  const messages = root.querySelector("[data-chat-messages]");
  const form = root.querySelector("[data-chat-form]");
  const input = root.querySelector("[data-chat-input]");
  const status = root.querySelector("[data-chat-status]");
  if (
    !messages ||
    !form ||
    !input ||
    !status ||
    (mode !== "global" && mode !== "direct")
  ) {
    return;
  }

  const seenIds = new Set();
  messages.querySelectorAll("[data-message-id]").forEach((node) => {
    seenIds.add(node.dataset.messageId);
  });

  const setStatus = (text) => {
    status.textContent = text;
  };

  const trimMessages = () => {
    while (messages.children.length > 200) {
      const oldest = messages.firstElementChild;
      if (!oldest) {
        return;
      }
      seenIds.delete(oldest.dataset.messageId);
      oldest.remove();
    }
  };

  const appendMessage = (payload) => {
    if (!payload || typeof payload !== "object") {
      return;
    }
    const payloadKeys = Object.keys(payload).sort();
    const expectedPayloadKeys =
      mode === "direct"
        ? ["conversation_id", "message", "scope"]
        : ["message", "scope"];
    if (
      payloadKeys.length !== expectedPayloadKeys.length ||
      !payloadKeys.every((key, index) => key === expectedPayloadKeys[index]) ||
      payload.scope !== mode ||
      (mode === "direct" && payload.conversation_id !== conversationId)
    ) {
      return;
    }
    const message = payload.message;
    if (!message || typeof message !== "object") {
      return;
    }
    const messageKeys = Object.keys(message).sort();
    const expectedMessageKeys = [
      "body",
      "created_at_iso",
      "id",
      "sender_username",
    ];
    if (
      messageKeys.length !== expectedMessageKeys.length ||
      !messageKeys.every((key, index) => key === expectedMessageKeys[index]) ||
      typeof message.id !== "string" ||
      typeof message.sender_username !== "string" ||
      typeof message.body !== "string" ||
      typeof message.created_at_iso !== "string" ||
      seenIds.has(message.id)
    ) {
      return;
    }

    const item = document.createElement("li");
    item.dataset.messageId = message.id;
    const sender = document.createElement("strong");
    sender.textContent = message.sender_username;
    const timestamp = document.createElement("time");
    timestamp.dateTime = message.created_at_iso;
    timestamp.textContent = message.created_at_iso;
    const body = document.createElement("p");
    body.className = "chat-body";
    body.textContent = message.body;
    item.append(sender, timestamp, body);
    messages.append(item);
    seenIds.add(message.id);
    trimMessages();
  };

  const socket = io("/chat", {
    auth: {
      csrf_token: csrfToken,
    },
  });

  const join = () => {
    const eventName =
      mode === "global" ? "chat:join_global" : "chat:join_direct";
    const payload =
      mode === "global" ? {} : { conversation_id: conversationId };
    socket.emit(eventName, payload, (ack) => {
      if (!ack || ack.ok !== true) {
        setStatus("채팅방에 연결하지 못했습니다.");
        return;
      }
      setStatus("실시간 채팅에 연결되었습니다.");
    });
  };

  socket.on("connect", join);
  socket.on("connect_error", () => {
    setStatus("실시간 채팅에 연결하지 못했습니다.");
  });
  socket.on("disconnect", () => {
    setStatus("실시간 채팅 연결이 종료되었습니다.");
  });
  socket.on("chat:error", () => {
    setStatus("요청을 처리하지 못했습니다.");
  });
  socket.on("chat:message", appendMessage);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const eventName =
      mode === "global" ? "chat:send_global" : "chat:send_direct";
    const payload =
      mode === "global"
        ? { body: input.value }
        : { conversation_id: conversationId, body: input.value };
    socket.emit(eventName, payload, (ack) => {
      if (!ack || ack.ok !== true) {
        setStatus(
          ack && ack.code === "rate_limited"
            ? "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
            : "메시지를 전송하지 못했습니다.",
        );
        return;
      }
      input.value = "";
      setStatus("메시지를 전송했습니다.");
    });
  });
})();
