// AIR AI Network - Production Chat Engine & UI Controller
// Supports: Dynamic Host, Session Auth, WebSocket Streaming, SSE Fallback, 3-Column Layout, Themes

// ── 1. Dynamic API Configuration (Zero Localhost on Phones) ─────
const API_CONFIG = {
  host: window.location.hostname || "127.0.0.1",
  port: window.location.port || (window.location.protocol === "https:" ? "443" : "80"),
  protocol: window.location.protocol,
  wsProtocol: window.location.protocol === "https:" ? "wss:" : "ws:",

  get origin() {
    return `${this.protocol}//${window.location.host}`;
  },
  get apiBase() {
    return `${this.origin}/api`;
  },
  get chatApi() {
    return `${this.apiBase}/chat`;
  },
  get uploadApi() {
    return `${this.apiBase}/files/upload`;
  },
  get wsChat() {
    const token = localStorage.getItem("hs_token") || "";
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : "";
    return `${this.wsProtocol}//${window.location.host}/ws/chat${tokenParam}`;
  }
};

// ── 2. State Management ─────────────────────────────────────────
let conversations = [];
let currentConvId = null;
let activeModelId = "llama3.2:latest";
let ws = null;
let isGenerating = false;
let currentAbortController = null;
let activeAttachment = null; // { url, name, size }
let latencyMs = 0;
let totalTokensGenerated = 0;
let lastFailedPayload = null;

// PWA Service Worker Registration
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(e => console.debug("SW registration:", e));
  });
}

// ── 3. Application Lifecycle ───────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  loadSavedConversations();
  setupComposerAutoResize();
  initWebSocket();
  pollStatusMetrics();
  setInterval(pollStatusMetrics, 2500);

  // Focus input
  const input = document.getElementById("chatInput");
  if (input && window.innerWidth > 768) {
    input.focus();
  }
});

// ── 4. Theme System (Dark, Light, System) ───────────────────────
function initTheme() {
  const saved = localStorage.getItem("hs_theme") || "dark";
  applyTheme(saved);
}

function applyTheme(theme) {
  const root = document.documentElement;
  localStorage.setItem("hs_theme", theme);
  const themeSelect = document.getElementById("themeSelect");
  if (themeSelect) themeSelect.value = theme;

  if (theme === "system") {
    const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
    root.setAttribute("data-theme", prefersLight ? "light" : "dark");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

function cycleTheme() {
  const current = localStorage.getItem("hs_theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
}

// ── 5. Responsive 3-Column Navigation ───────────────────────────
function toggleLeftSidebar() {
  const sidebar = document.getElementById("sidebarLeft");
  const backdrop = document.getElementById("drawerBackdrop");
  if (!sidebar) return;

  if (window.innerWidth <= 768) {
    sidebar.classList.toggle("open");
    backdrop.classList.toggle("active", sidebar.classList.contains("open"));
  } else {
    sidebar.classList.toggle("collapsed");
  }
}

function toggleRightSidebar() {
  const sidebar = document.getElementById("sidebarRight");
  const backdrop = document.getElementById("drawerBackdrop");
  if (!sidebar) return;

  if (window.innerWidth <= 1024) {
    sidebar.classList.toggle("open");
    backdrop.classList.toggle("active", sidebar.classList.contains("open"));
  } else {
    sidebar.classList.toggle("collapsed");
  }
}

function closeAllDrawers() {
  const left = document.getElementById("sidebarLeft");
  const right = document.getElementById("sidebarRight");
  const backdrop = document.getElementById("drawerBackdrop");
  if (left) left.classList.remove("open");
  if (right) right.classList.remove("open");
  if (backdrop) backdrop.classList.remove("active");
}

// ── 6. WebSocket Connection Lifecycle ───────────────────────────
function initWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  const reconnectBanner = document.getElementById("reconnectBanner");

  try {
    ws = new WebSocket(API_CONFIG.wsChat);

    ws.onopen = () => {
      console.log("[WS] Connected to AIR AI host");
      if (reconnectBanner) reconnectBanner.style.display = "none";
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleIncomingWsMessage(data);
      } catch (err) {
        console.error("[WS] Parse error:", err);
      }
    };

    ws.onclose = (event) => {
      console.log("[WS] Closed code:", event.code);
      if (event.code === 4401) {
        // Auth required
        alert("Session expired or authentication required. Returning to portal.");
        window.location.href = "/";
        return;
      }
      if (reconnectBanner) reconnectBanner.style.display = "block";
      setTimeout(initWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.warn("[WS] Error encountered, falling back to HTTP SSE if needed:", err);
    };
  } catch (e) {
    console.error("[WS] Initialization exception:", e);
    setTimeout(initWebSocket, 3000);
  }
}

let isWebSearchEnabled = true;

function toggleWebSearch() {
  isWebSearchEnabled = !isWebSearchEnabled;
  const btn = document.getElementById("btnWebSearch");
  const input = document.getElementById("chatInput");
  if (btn) {
    if (isWebSearchEnabled) {
      btn.classList.add("active");
      btn.innerHTML = '🌐 <span class="web-toggle-text">Web ON</span>';
      btn.title = "Web Search ON: Real-time web results enabled";
      if (input) input.placeholder = "Ask AIR AI (Web search enabled)...";
    } else {
      btn.classList.remove("active");
      btn.innerHTML = '🌐 <span class="web-toggle-text">Web OFF</span>';
      btn.title = "Web Search OFF: Answering strictly from local weights";
      if (input) input.placeholder = "Ask AIR AI (Offline local mode)...";
    }
  }
}

function renderWebSearchResults(query, results) {
  const assistantBubbles = document.querySelectorAll(".msg-assistant-bubble");
  if (assistantBubbles.length === 0) return;
  const lastBubble = assistantBubbles[assistantBubbles.length - 1];

  if (lastBubble.parentElement.querySelector(".web-search-banner")) return;

  const banner = document.createElement("div");
  banner.className = "web-search-banner";
  let sourcesHtml = "";
  if (results && results.length > 0) {
    sourcesHtml = '<div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:4px;">' +
      results.map((r, i) => `<a class="web-source-chip" href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(r.snippet || r.title)}">🔗 ${escapeHtml(r.title)}</a>`).join("") +
      '</div>';
  }
  banner.innerHTML = `<div><b>🌐 Searched web:</b> <i>"${escapeHtml(query)}"</i> (${results ? results.length : 0} results)</div>${sourcesHtml}`;
  lastBubble.parentElement.insertBefore(banner, lastBubble);
}

function handleIncomingWsMessage(data) {
  if (data.type === "search_results") {
    renderWebSearchResults(data.query, data.results);
  } else if (data.type === "token") {
    appendStreamingToken(data.token);
    totalTokensGenerated++;
    const tokensEl = document.getElementById("inspTokens");
    if (tokensEl) tokensEl.innerText = totalTokensGenerated;
  } else if (data.type === "done") {
    finalizeStreamingMessage();
  } else if (data.type === "status") {
    const speedEl = document.getElementById("tokenSpeedBadge");
    if (speedEl) speedEl.innerText = data.status || "Generating...";
  } else if (data.type === "error") {
    handleStreamError(data.error);
  }
}

// ── 7. Message Sending & Token Streaming ───────────────────────
async function sendMessage() {
  if (isGenerating) return;

  const input = document.getElementById("chatInput");
  const rawText = input ? input.value.trim() : "";

  if (!rawText && !activeAttachment) return;

  // Ensure conversation exists
  let conv = getCurrentConv();
  if (!conv) {
    startNewChat();
    conv = getCurrentConv();
  }

  // Clear input & reset size
  if (input) {
    input.value = "";
    input.style.height = "auto";
  }

  // Hide empty welcome hero
  const emptyWelcome = document.getElementById("emptyWelcome") || document.querySelector(".empty-welcome");
  if (emptyWelcome) emptyWelcome.style.display = "none";

  // Append user message
  const userMsg = {
    role: "user",
    content: rawText,
    attachment: activeAttachment ? { ...activeAttachment } : null,
    timestamp: Date.now()
  };
  conv.messages.push(userMsg);
  appendMessageDOM("user", rawText, userMsg.attachment);
  clearAttachment();

  // Prepare assistant placeholder message
  setGeneratingState(true);
  window.currentStreamingText = "";
  appendMessageDOM("assistant", "", null, true);

  // Construct request payload
  const payload = {
    conversation_id: conv.id,
    model: activeModelId,
    message: rawText,
    messages: conv.messages.map(m => ({ role: m.role, content: m.content })),
    temperature: getTemperatureSetting(),
    stream: true,
    web_search: isWebSearchEnabled
  };
  lastFailedPayload = payload;

  // Attempt via WebSocket first; fallback to HTTP SSE if unavailable
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({
        type: "chat",
        prompt: rawText,
        model: activeModelId,
        conversation_id: conv.id,
        temperature: payload.temperature,
        web_search: isWebSearchEnabled
      }));
    } catch (e) {
      console.warn("[WS] Send failed, switching to HTTP SSE fallback:", e);
      fallbackHttpStream(payload);
    }
  } else {
    fallbackHttpStream(payload);
  }
}

function appendStreamingToken(token) {
  window.currentStreamingText = (window.currentStreamingText || "") + token;
  const assistantBubbles = document.querySelectorAll(".msg-assistant-bubble");
  if (assistantBubbles.length > 0) {
    const lastBubble = assistantBubbles[assistantBubbles.length - 1];
    lastBubble.innerHTML = formatMessageContent(window.currentStreamingText);
    scrollMessagesToBottom();
  }
}

function finalizeStreamingMessage() {
  const conv = getCurrentConv();
  if (conv && window.currentStreamingText) {
    conv.messages.push({
      role: "assistant",
      content: window.currentStreamingText,
      timestamp: Date.now()
    });
    saveConversations();
  }
  setGeneratingState(false);
  window.currentStreamingText = "";
}

function handleStreamError(errMsg) {
  setGeneratingState(false);
  const safeMsg = errMsg ? escapeHtml(String(errMsg)) : "Local AI model is offline or unreachable.";
  const assistantBubbles = document.querySelectorAll(".msg-assistant-bubble");
  if (assistantBubbles.length > 0) {
    const lastBubble = assistantBubbles[assistantBubbles.length - 1];
    lastBubble.innerHTML = `
      <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 12px 14px;">
        <div style="font-weight: 700; color: var(--accent-red); margin-bottom: 4px;">AIR AI INFERENCE ERROR</div>
        <div style="font-size: 0.84rem; color: var(--text-secondary); line-height: 1.5; white-space: pre-wrap;">${safeMsg}</div>
        <div style="margin-top: 10px;">
          <button class="btn btn-secondary btn-sm" onclick="retryLastMessage()">[ RETRY ]</button>
        </div>
      </div>
    `;
  }
}

function retryLastMessage() {
  if (lastFailedPayload) {
    setGeneratingState(true);
    window.currentStreamingText = "";
    appendMessageDOM("assistant", "", null, true);
    fallbackHttpStream(lastFailedPayload);
  }
}

// ── 8. HTTP SSE Streaming Fallback ──────────────────────────────
async function fallbackHttpStream(payload) {
  currentAbortController = new AbortController();
  const token = localStorage.getItem("hs_token") || "";

  try {
    const res = await fetch(API_CONFIG.chatApi, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "Authorization": `Bearer ${token}` } : {})
      },
      body: JSON.stringify(payload),
      signal: currentAbortController.signal
    });

    if (!res.ok) {
      if (res.status === 401) {
        alert("Session expired. Please reconnect.");
        window.location.href = "/";
        return;
      }
      const err = await res.json().catch(() => ({ detail: "Engine error" }));
      handleStreamError(err.detail || `Server status ${res.status}`);
      return;
    }

    if (!res.body || !res.body.getReader) {
      // Universal fallback for older phones/tablets without ReadableStream support
      const text = await res.text();
      const lines = text.split("\n\n");
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const parsed = JSON.parse(line.slice(6).trim());
            if (parsed.token) appendStreamingToken(parsed.token);
          } catch (e) {}
        }
      }
      finalizeStreamingMessage();
      return;
    }

    const reader = res.body.getReader();
    const decoder = typeof TextDecoder !== "undefined" ? new TextDecoder() : { decode: (v) => String.fromCharCode.apply(null, v) };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split("\n\n");
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const raw = line.slice(6).trim();
          try {
            const parsed = JSON.parse(raw);
            if (parsed.type === "search_results") {
              renderWebSearchResults(parsed.query, parsed.results);
            }
            if (parsed.error) {
              handleStreamError(parsed.error);
              return;
            }
            if (parsed.token) {
              appendStreamingToken(parsed.token);
              totalTokensGenerated++;
            }
            if (parsed.done) {
              finalizeStreamingMessage();
              return;
            }
          } catch (e) {}
        }
      }
    }
    finalizeStreamingMessage();
  } catch (e) {
    if (e.name !== "AbortError") {
      handleStreamError(String(e));
    }
  } finally {
    setGeneratingState(false);
  }
}

function stopGeneration() {
  if (currentAbortController) {
    currentAbortController.abort();
  }
  setGeneratingState(false);
}

function setGeneratingState(generating) {
  isGenerating = generating;
  const btnSend = document.getElementById("btnSend");
  const btnStop = document.getElementById("btnStop");
  const speedEl = document.getElementById("tokenSpeedBadge");

  if (btnSend) btnSend.style.display = generating ? "none" : "inline-flex";
  if (btnStop) btnStop.style.display = generating ? "inline-flex" : "none";
  if (speedEl) speedEl.innerText = generating ? "Generating tokens..." : "Ready";
}

// ── 9. DOM Message Rendering ───────────────────────────────────
function appendMessageDOM(role, content, attachment = null, isStreaming = false) {
  const viewport = document.getElementById("messagesViewport");
  if (!viewport) return;

  const row = document.createElement("div");
  row.className = "message-row";

  const isUser = role === "user";
  const avatar = document.createElement("div");
  avatar.className = `msg-avatar ${isUser ? 'msg-avatar-user' : 'msg-avatar-ai'}`;
  avatar.innerText = isUser ? "U" : "AI";

  const wrapper = document.createElement("div");
  wrapper.className = "msg-content-wrapper";

  const header = document.createElement("div");
  header.className = "msg-header";
  header.innerHTML = `<span>${isUser ? 'You' : 'AIR AI'}</span>`;

  const bubble = document.createElement("div");
  bubble.className = `msg-bubble ${isUser ? 'msg-user-bubble' : 'msg-assistant-bubble'}`;

  if (isStreaming) {
    bubble.innerHTML = `<span style="color:var(--text-muted); font-style:italic;">AIR AI is thinking...</span>`;
  } else {
    bubble.innerHTML = formatMessageContent(content);
  }

  if (attachment) {
    const attDiv = document.createElement("div");
    attDiv.style.margin = "8px 0";
    if (attachment.url && attachment.url.match(/\.(jpeg|jpg|png|webp|gif)$/i)) {
      attDiv.innerHTML = `<img src="${attachment.url}" style="max-width: 240px; border-radius: 6px; border: 1px solid var(--border-subtle);" alt="attachment">`;
    } else {
      attDiv.innerHTML = `<div style="font-size:0.8rem; color:var(--accent-cyan);">📎 ${escapeHtml(attachment.name || 'File')}</div>`;
    }
    wrapper.appendChild(attDiv);
  }

  wrapper.appendChild(header);
  wrapper.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(wrapper);
  viewport.appendChild(row);

  scrollMessagesToBottom();
}

function formatMessageContent(text) {
  if (!text) return "";
  let escaped = escapeHtml(text);
  // Code blocks
  escaped = escaped.replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code class="language-${lang}">${code}</code></pre>`;
  });
  // Inline code
  escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Paragraphs
  return escaped.replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br>");
}

function scrollMessagesToBottom() {
  const viewport = document.getElementById("messagesViewport");
  if (viewport) {
    viewport.scrollTop = viewport.scrollHeight;
  }
}

// ── 10. File & Attachment Handling ──────────────────────────────
async function handleFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  const token = localStorage.getItem("hs_token") || "";

  try {
    const res = await fetch(API_CONFIG.uploadApi, {
      method: "POST",
      headers: token ? { "Authorization": `Bearer ${token}` } : {},
      body: formData
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      alert(`Upload error: ${data.detail || 'Failed to upload'}`);
      return;
    }

    activeAttachment = {
      url: data.url,
      name: data.original_name,
      size: data.size_bytes
    };

    const preview = document.getElementById("attachmentPreview");
    const previewImg = document.getElementById("previewImg");
    const previewName = document.getElementById("previewName");

    if (preview && previewName) {
      previewName.innerText = data.original_name;
      if (file.type.startsWith("image/")) {
        previewImg.src = URL.createObjectURL(file);
        previewImg.style.display = "block";
      } else {
        previewImg.style.display = "none";
      }
      preview.style.display = "flex";
    }
  } catch (err) {
    alert(`File upload failed: ${err.message}`);
  }
}

function clearAttachment() {
  activeAttachment = null;
  const preview = document.getElementById("attachmentPreview");
  const fileInput = document.getElementById("fileInput");
  if (preview) preview.style.display = "none";
  if (fileInput) fileInput.value = "";
}

// ── 11. Conversation Management ─────────────────────────────────
function getCurrentConv() {
  return conversations.find(c => c.id === currentConvId);
}

function startNewChat() {
  const newId = "c_" + Date.now().toString(36);
  const conv = {
    id: newId,
    title: "New Conversation",
    messages: [],
    created_at: Date.now()
  };
  conversations.unshift(conv);
  currentConvId = newId;
  saveConversations();
  renderConvList();
  renderCurrentConversation();
  closeAllDrawers();
}

function selectConversation(id) {
  currentConvId = id;
  renderConvList();
  renderCurrentConversation();
  closeAllDrawers();
}

function deleteConversation(id, event) {
  if (event) event.stopPropagation();
  conversations = conversations.filter(c => c.id !== id);
  if (currentConvId === id) {
    currentConvId = conversations.length > 0 ? conversations[0].id : null;
  }
  saveConversations();
  renderConvList();
  renderCurrentConversation();
}

function renderConvList() {
  const listEl = document.getElementById("convList");
  if (!listEl) return;
  listEl.innerHTML = "";

  conversations.forEach(c => {
    const item = document.createElement("div");
    item.className = `conv-item ${c.id === currentConvId ? 'active' : ''}`;
    item.onclick = () => selectConversation(c.id);

    const titleSpan = document.createElement("span");
    titleSpan.className = "conv-title";
    titleSpan.innerText = c.title || "Untitled Chat";

    const delBtn = document.createElement("span");
    delBtn.className = "btn-delete-conv";
    delBtn.innerHTML = "✕";
    delBtn.title = "Delete conversation";
    delBtn.onclick = (e) => deleteConversation(c.id, e);

    item.appendChild(titleSpan);
    item.appendChild(delBtn);
    listEl.appendChild(item);
  });
}

function renderCurrentConversation() {
  const viewport = document.getElementById("messagesViewport");
  if (!viewport) return;
  viewport.innerHTML = "";

  const conv = getCurrentConv();
  if (!conv || conv.messages.length === 0) {
    viewport.innerHTML = `
      <div id="emptyWelcome" style="text-align: center; margin: auto; max-width: 520px; padding: 24px 16px;">
        <div class="portal-logo" style="width: 54px; height: 54px; font-size: 1.5rem; margin-bottom: 12px;">AIR</div>
        <div class="brand-subtitle" style="margin-bottom: 6px;">LOCAL INTELLIGENCE NETWORK</div>
        <h2 style="font-size: 1.6rem; font-weight: 800; margin-bottom: 10px;">Private Offline AIR AI</h2>
        <p style="color: var(--text-secondary); font-size: 0.92rem; line-height: 1.6; margin-bottom: 16px;">
          All inference runs locally on the host laptop's GPU. Prompts and conversations never leave the private Wi-Fi network.
        </p>
        <div style="margin-bottom: 20px; font-size: 0.76rem; color: var(--text-muted);">
          All rights reserved HS Solution: <a href="https://hs-ai-studio.onrender.com/" target="_blank" rel="noopener noreferrer" style="color: var(--accent-cyan); text-decoration: underline;">https://hs-ai-studio.onrender.com/</a>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;">
          <button class="btn btn-secondary btn-sm" onclick="usePrompt('Explain how an air-gapped offline local LLM operates')">"How offline LLMs work"</button>
          <button class="btn btn-secondary btn-sm" onclick="usePrompt('Analyze the difference between symmetric and asymmetric encryption')">"Explain encryption basics"</button>
          <button class="btn btn-secondary btn-sm" onclick="usePrompt('Write a clean Python script for local network discovery')">"Python network discovery"</button>
        </div>
      </div>
    `;
    return;
  }

  conv.messages.forEach(m => {
    appendMessageDOM(m.role, m.content, m.attachment, false);
  });
}

function saveConversations() {
  try {
    localStorage.setItem("hs_conversations", JSON.stringify(conversations));
  } catch (e) {}
}

function loadSavedConversations() {
  try {
    const raw = localStorage.getItem("hs_conversations");
    if (raw) {
      conversations = JSON.parse(raw);
      if (conversations.length > 0) {
        currentConvId = conversations[0].id;
      }
    }
  } catch (e) {
    conversations = [];
  }
  if (conversations.length === 0) {
    startNewChat();
  } else {
    renderConvList();
    renderCurrentConversation();
  }
}

// ── 12. Real-Time Telemetry & Status Polling (Section 21) ───────
async function pollStatusMetrics() {
  const t0 = performance.now();
  try {
    const res = await fetch("/api/health");
    const t1 = performance.now();
    latencyMs = Math.round(t1 - t0);

    const latHdr = document.getElementById("hdrLatency");
    const latInsp = document.getElementById("inspLatency");
    if (latHdr) latHdr.innerText = `${latencyMs} ms`;
    if (latInsp) latInsp.innerText = `${latencyMs} ms`;

    // Fetch deep status
    const sRes = await fetch("/api/status");
    if (sRes.ok) {
      const s = await sRes.json();
      if (s.model && s.model.name) {
        activeModelId = s.model.name;
        const cleanName = activeModelId.replace(":latest", "");
        const mHdr = document.getElementById("hdrModelName");
        const mInsp = document.getElementById("inspModelName");
        if (mHdr) mHdr.innerText = cleanName;
        if (mInsp) mInsp.innerText = cleanName;
      }
      if (s.model && s.model.speed_tokens_per_sec !== undefined) {
        const speedInsp = document.getElementById("inspSpeed");
        if (speedInsp) speedInsp.innerText = s.model.speed_tokens_per_sec;
      }
      if (s.network && s.network.host_ip) {
        const hostIpEl = document.getElementById("inspHostIp");
        if (hostIpEl) hostIpEl.innerText = s.network.host_ip;
      }
    }
  } catch (e) {
    const latHdr = document.getElementById("hdrLatency");
    if (latHdr) latHdr.innerText = "offline";
  }
}

// ── 13. Client Connection Diagnostics (Section 15) ──────────────
async function updateClientDiagnostics() {
  const hostEl = document.getElementById("diagClientHost");
  if (hostEl) hostEl.innerText = API_CONFIG.host;

  const feEl = document.getElementById("diagClientFrontend");
  if (feEl) feEl.innerText = API_CONFIG.origin;

  const apiEl = document.getElementById("diagClientApi");
  if (apiEl) apiEl.innerText = API_CONFIG.apiBase;

  const wsEl = document.getElementById("diagClientWs");
  if (wsEl) wsEl.innerText = API_CONFIG.wsChat.split("?")[0];

  const modelEl = document.getElementById("diagClientModel");
  if (modelEl) modelEl.innerText = activeModelId.replace(":latest", "");

  const statusEl = document.getElementById("diagClientStatus");
  const latEl = document.getElementById("diagClientLatency");

  const t0 = performance.now();
  try {
    const res = await fetch("/api/health");
    const t1 = performance.now();
    const lat = Math.round(t1 - t0);

    if (latEl) latEl.innerText = `${lat} ms`;
    if (statusEl) {
      statusEl.innerText = res.ok ? "● Online" : `● HTTP ${res.status}`;
      statusEl.style.color = res.ok ? "var(--accent-green)" : "var(--accent-amber)";
    }
  } catch (e) {
    if (statusEl) {
      statusEl.innerText = "● Unreachable";
      statusEl.style.color = "var(--accent-red)";
    }
    if (latEl) latEl.innerText = "-- ms";
  }
}

// ── 14. Input & Composer Helpers ────────────────────────────────
function handleKeyDown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function usePrompt(text) {
  const input = document.getElementById("chatInput");
  if (input) {
    input.value = text;
    sendMessage();
  }
}

function setupComposerAutoResize() {
  const textarea = document.getElementById("chatInput");
  if (!textarea) return;

  textarea.addEventListener("input", function() {
    this.style.height = "auto";
    this.style.height = `${Math.min(this.scrollHeight, 140)}px`;
  });
}

function getTemperatureSetting() {
  const slider = document.getElementById("tempSlider");
  return slider ? parseFloat(slider.value) : 0.7;
}

// ── 15. Modal Helpers ───────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("active");
  if (id === "settingsModal") {
    updateClientDiagnostics();
  }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("active");
}

function saveSettings() {
  closeModal("settingsModal");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

