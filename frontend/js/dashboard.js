// AIR AI Host Dashboard Manager - Enterprise Appliance Controller
let dashboardData = null;
let selectedNewModel = null;
let pinExpiresSeconds = 0;
let pinTimerInterval = null;

window.addEventListener("DOMContentLoaded", () => {
  refreshDashboard();
  refreshPinStatus();
  refreshDevicesTable();
  setInterval(refreshDashboard, 2000);
  setInterval(refreshPinStatus, 5000);
});

// ── 1. Section Navigation ───────────────────────────────────────
function switchSection(secId) {
  const sections = ["overview", "security", "devices", "model", "network"];
  sections.forEach(s => {
    const el = document.getElementById(`sec-${s}`);
    if (el) el.style.display = (s === secId) ? "block" : "none";
  });

  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach(btn => {
    btn.classList.toggle("active", btn.innerText.toLowerCase().includes(secId));
  });

  if (secId === "devices") refreshDevicesTable();
  if (secId === "security") refreshPinStatus();
}

// ── 2. Metric Polling & Dashboard Rendering ─────────────────────
async function refreshDashboard() {
  try {
    const res = await fetch("/api/dashboard");
    if (!res.ok) return;
    const data = await res.json();
    dashboardData = data;
    renderDashboard(data);
  } catch (e) {
    console.debug("Dashboard poll failed", e);
  }
}

function renderDashboard(data) {
  // System Metrics
  const sys = data.system || {};
  document.getElementById("cpuVal").innerText = `${sys.cpu_percent || 0}%`;
  document.getElementById("cpuPctText").innerText = `${sys.cpu_percent || 0}%`;
  document.getElementById("cpuBar").style.width = `${Math.min(100, sys.cpu_percent || 0)}%`;

  document.getElementById("ramVal").innerText = `${sys.ram_percent || 0}%`;
  document.getElementById("ramGbText").innerText = `${sys.ram_total_gb ? (sys.ram_total_gb - sys.ram_available_gb).toFixed(1) : 0} / ${sys.ram_total_gb || 0} GB`;
  document.getElementById("ramBar").style.width = `${Math.min(100, sys.ram_percent || 0)}%`;

  document.getElementById("gpuVal").innerText = `${sys.gpu_percent || 0}%`;
  document.getElementById("gpuNameText").innerText = sys.gpu_name || "NVIDIA / Integrated";
  document.getElementById("gpuBar").style.width = `${Math.min(100, sys.gpu_percent || 0)}%`;

  document.getElementById("vramVal").innerText = `${sys.vram_percent || 0}%`;
  document.getElementById("vramGbText").innerText = `${sys.vram_total_gb || 0} GB Total`;
  document.getElementById("vramBar").style.width = `${Math.min(100, sys.vram_percent || 0)}%`;

  // AI Engine
  const ai = data.ai_engine || {};
  document.getElementById("activeModelLabel").innerText = (ai.model_name || "None").replace(":latest", "");
  document.getElementById("tokenSpeedVal").innerText = ai.tokens_per_second || 0;
  document.getElementById("activeRequestsVal").innerText = ai.active_requests || 0;
  document.getElementById("queuedRequestsVal").innerText = `${ai.queued_requests || 0} queued`;

  const engBadge = document.getElementById("engineStatusBadge");
  if (ai.is_loaded) {
    engBadge.className = "badge-status badge-online";
    engBadge.innerText = "● Running";
  } else {
    engBadge.className = "badge-status badge-warn";
    engBadge.innerText = "● Stopped";
  }

  // Network Overview
  const net = data.network || {};
  document.getElementById("dashHostIp").innerText = net.host_ip || "192.168.137.1";
  document.getElementById("dashConnectedCount").innerText = (data.clients && data.clients.total) || 0;

  // QR Code
  renderQrCode();
}

// ── 3. Host Access PIN Manager (Section 3) ──────────────────────
async function refreshPinStatus() {
  try {
    const res = await fetch("/api/admin/pin");
    if (!res.ok) return;
    const data = await res.json();

    const pinEl = document.getElementById("displayCurrentPin");
    const expEl = document.getElementById("displayPinExpires");
    const chk = document.getElementById("chkRequirePin");
    const secAuth = document.getElementById("secStatusAuth");

    if (chk) chk.checked = data.require_pin;
    if (secAuth) {
      secAuth.innerHTML = data.require_pin ? `<span style="color:var(--accent-green)">● ACTIVE</span>` : `<span style="color:var(--text-muted)">○ DISABLED</span>`;
    }

    if (pinEl) {
      pinEl.innerText = data.require_pin ? data.current_pin : "DISABLED";
      pinEl.style.opacity = data.require_pin ? "1" : "0.5";
    }

    pinExpiresSeconds = data.expires_in_seconds || 0;
    updatePinCountdown();

    if (!pinTimerInterval) {
      pinTimerInterval = setInterval(() => {
        if (pinExpiresSeconds > 0) {
          pinExpiresSeconds--;
          updatePinCountdown();
        }
      }, 1000);
    }
  } catch (e) {
    console.debug("Failed to fetch PIN status:", e);
  }
}

function updatePinCountdown() {
  const expEl = document.getElementById("displayPinExpires");
  if (!expEl) return;
  const mins = Math.floor(pinExpiresSeconds / 60);
  const secs = pinExpiresSeconds % 60;
  expEl.innerText = `Expires in: ${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

async function generateNewPin() {
  try {
    const res = await fetch("/api/admin/pin/generate", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      refreshPinStatus();
    }
  } catch (e) {
    alert("Failed to generate new PIN: " + e.message);
  }
}

async function togglePinRequirement(checked) {
  try {
    const res = await fetch("/api/admin/pin/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ require_pin: checked })
    });
    refreshPinStatus();
  } catch (e) {
    alert("Failed to update PIN setting: " + e.message);
  }
}

// ── 4. Connected Devices & Sessions (Section 5) ─────────────────
async function refreshDevicesTable() {
  const tbody = document.getElementById("devicesTableBody");
  if (!tbody) return;

  try {
    const [devRes, sessRes] = await Promise.all([
      fetch("/api/devices"),
      fetch("/api/admin/sessions")
    ]);

    const devData = await devRes.json();
    const sessData = await sessRes.json();

    const devices = devData.devices || [];
    const sessions = sessData.sessions || [];

    if (devices.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">No external devices connected. Join via Mobile Hotspot.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    devices.forEach(d => {
      const isBlocked = d.is_blocked || false;
      const devSessions = sessions.filter(s => s.client_ip === d.ip);
      const hasActiveSession = devSessions.some(s => s.status === "Active");

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>
          <b>${escapeHtml(d.friendly_name || d.hostname || 'Device')}</b>
          <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(d.vendor || 'Local Client')}</div>
        </td>
        <td>${escapeHtml(d.device_type || 'Unknown')}</td>
        <td>${escapeHtml(d.os || 'Unknown')}</td>
        <td style="font-family:var(--font-mono); color:var(--accent-cyan);">${d.ip}</td>
        <td>
          ${hasActiveSession ? '<span class="badge-status badge-online">Active</span>' : '<span class="badge-status badge-warn">Idle</span>'}
        </td>
        <td>${d.last_seen_relative || 'Just now'}</td>
        <td>
          <div style="display:flex; gap:6px;">
            ${isBlocked 
              ? `<button class="btn btn-secondary btn-sm" onclick="unblockDevice('${d.ip}')">Unblock</button>` 
              : `<button class="btn btn-danger btn-sm" onclick="blockDevice('${d.ip}')">Block</button>`}
            ${devSessions.length > 0 ? `<button class="btn btn-secondary btn-sm" onclick="revokeSession('${devSessions[0].token}')">Revoke</button>` : ''}
            <button class="btn btn-secondary btn-sm" onclick="alert('Device: ${escapeHtml(d.friendly_name || d.ip)}\\nIP: ${d.ip}\\nOS: ${d.os}\\nUser-Agent: ${escapeHtml(d.user_agent || 'N/A')}')">Details</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--accent-red); padding:16px;">Failed to load devices: ${e.message}</td></tr>`;
  }
}

async function blockDevice(ip) {
  if (confirm(`Block device at IP ${ip}? This will revoke all sessions and drop connections.`)) {
    await fetch("/api/devices/block", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip })
    });
    refreshDevicesTable();
  }
}

async function unblockDevice(ip) {
  await fetch("/api/devices/unblock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip })
  });
  refreshDevicesTable();
}

async function revokeSession(token) {
  if (confirm("Revoke this client's active session?")) {
    await fetch("/api/admin/sessions/revoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token })
    });
    refreshDevicesTable();
  }
}

// ── 5. AI Inference Diagnostics (Section 14) ────────────────────
async function runAiInferenceTest() {
  openModal("testAiModal");
  const badge = document.getElementById("testAiBadge");
  const modelEl = document.getElementById("testAiModel");
  const statusEl = document.getElementById("testAiStatus");
  const latEl = document.getElementById("testAiLatency");
  const respEl = document.getElementById("testAiResponse");
  const btn = document.getElementById("btnRerunAiTest");

  if (badge) {
    badge.className = "badge-status badge-warn";
    badge.innerText = "RUNNING";
  }
  if (statusEl) statusEl.innerHTML = `<span class="badge-status badge-warn">● Running Inference...</span>`;
  if (latEl) latEl.innerText = "Measuring...";
  if (respEl) respEl.innerText = "Waiting for model response...";
  if (btn) btn.disabled = true;

  const t0 = performance.now();
  try {
    const res = await fetch("/api/test-inference", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "Say hello" })
    });
    const t1 = performance.now();
    const latency = Math.round(t1 - t0);

    const data = await res.json();
    if (latEl) latEl.innerText = `${latency}ms`;

    if (data.success) {
      if (badge) {
        badge.className = "badge-status badge-online";
        badge.innerText = "PASS";
      }
      if (modelEl) modelEl.innerText = (data.model || "llama3.2").replace(":latest", "");
      if (statusEl) statusEl.innerHTML = `<span class="badge-status badge-online">● Online</span>`;
      if (respEl) respEl.innerText = `"${data.response}"`;
    } else {
      if (badge) {
        badge.className = "badge-status badge-warn";
        badge.innerText = "FAIL";
      }
      if (statusEl) statusEl.innerHTML = `<span class="badge-status badge-warn" style="color:var(--accent-red)">● Error</span>`;
      if (respEl) respEl.innerText = `Error: ${data.error || 'Failed to infer'}`;
    }
  } catch (err) {
    if (badge) {
      badge.className = "badge-status badge-warn";
      badge.innerText = "FAIL";
    }
    if (statusEl) statusEl.innerHTML = `<span class="badge-status badge-warn" style="color:var(--accent-red)">● Unreachable</span>`;
    if (respEl) respEl.innerText = `Network Error: ${err.message || String(err)}`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── 6. QR Code & Network Utilities ──────────────────────────────
async function renderQrCode() {
  const container = document.getElementById("modalQrContainer");
  if (!container || container.children.length > 0) return;
  try {
    const res = await fetch("/api/network/qr");
    if (res.ok) {
      const svg = await res.text();
      container.innerHTML = svg;
    }
  } catch (e) {}
}

function copyClientAddress() {
  const hostIp = (dashboardData && dashboardData.network && dashboardData.network.host_ip) || "192.168.137.1";
  const url = `http://${hostIp}/`;
  navigator.clipboard.writeText(url).then(() => {
    alert(`Copied client access URL: ${url}`);
  });
}

async function runNetworkDiagnostics() {
  const btn = document.getElementById("btnRunNetDiag");
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Running Diagnostics...";
  }

  try {
    const res = await fetch("/api/network/diagnostics");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // 1. Hotspot
    const hsEl = document.getElementById("diagHotspotStatus");
    const hsDet = document.getElementById("diagHotspotDetail");
    if (hsEl) {
      hsEl.innerText = `● ${data.hotspot.status}`;
      hsEl.style.color = data.hotspot.verified ? "var(--accent-green)" : "var(--accent-yellow)";
    }
    if (hsDet) hsDet.innerText = `Adapter: ${data.hotspot.adapter}`;

    // 2. IP
    const ipEl = document.getElementById("diagHostIp");
    const ipDet = document.getElementById("diagIpDetail");
    if (ipEl) ipEl.innerText = data.hotspot_ip.ip;
    if (ipDet) ipDet.innerText = data.hotspot_ip.is_default_hotspot_subnet ? "Mobile Hotspot subnet" : "Assigned subnet";

    // 3. DHCP
    const dhcpEl = document.getElementById("diagDhcpStatus");
    const dhcpDet = document.getElementById("diagDhcpDetail");
    if (dhcpEl) {
      dhcpEl.innerText = `● ${data.dhcp.status}`;
      dhcpEl.style.color = data.dhcp.verified ? "var(--accent-green)" : "var(--accent-yellow)";
    }
    if (dhcpDet) dhcpDet.innerText = data.dhcp.detail;

    // 4. DNS
    const dnsEl = document.getElementById("diagDnsStatus");
    const dnsDet = document.getElementById("diagDnsDetail");
    if (dnsEl) {
      dnsEl.innerText = `● ${data.dns.status}`;
      dnsEl.style.color = (!data.dns.fallback_mode && data.dns.running) ? "var(--accent-green)" : "var(--accent-yellow)";
    }
    if (dnsDet) dnsDet.innerText = data.dns.detail;

    // 5. HTTP
    const httpEl = document.getElementById("diagHttpStatus");
    const httpDet = document.getElementById("diagHttpDetail");
    if (httpEl) {
      httpEl.innerText = `● ${data.http.status}`;
      httpEl.style.color = data.http.verified ? "var(--accent-green)" : "var(--accent-red)";
    }
    if (httpDet) httpDet.innerText = `Port 80: ${data.http.port_80 ? '✓' : '✗'} | Port 8000: ${data.http.port_api ? '✓' : '✗'}`;

    // 6. Captive Portal
    const cpEl = document.getElementById("diagCpStatus");
    if (cpEl) {
      cpEl.innerText = `● ${data.captive_portal.status}`;
      cpEl.style.color = data.captive_portal.verified ? "var(--accent-green)" : "var(--accent-red)";
    }

    // 7. Connectivity Check
    const ccEl = document.getElementById("diagCcStatus");
    const ccDet = document.getElementById("diagCcDetail");
    if (ccEl) {
      ccEl.innerText = `● ${data.connectivity_check.status}`;
      ccEl.style.color = data.connectivity_check.detected ? "var(--accent-green)" : "var(--accent-yellow)";
    }
    if (ccDet) ccDet.innerText = `${data.connectivity_check.probe_count} probes recorded`;

    // 8. Firewall
    const fwEl = document.getElementById("diagFwStatus");
    const fwDet = document.getElementById("diagFwDetail");
    if (fwEl) {
      fwEl.innerText = `● ${data.firewall.status}`;
      fwEl.style.color = data.firewall.accessible ? "var(--accent-green)" : "var(--accent-yellow)";
    }
    if (fwDet) fwDet.innerText = data.firewall.windows_firewall_rules;

    // Fallback URL
    const fbUrl = document.getElementById("netFallbackUrl");
    if (fbUrl) fbUrl.innerText = data.portal_url || `http://${data.hotspot_ip.ip}/`;

    // QR Image refresh
    const qrImg = document.getElementById("netTabQrImg");
    if (qrImg) qrImg.src = `/api/network/qr?t=${Date.now()}`;
  } catch (err) {
    console.error("Diagnostics check failed:", err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "[ RUN NETWORK TEST ]";
    }
  }
}

// Auto-run diagnostics on tab switch
const origSwitchSection = switchSection;
switchSection = function(secId) {
  origSwitchSection(secId);
  if (secId === "network") {
    runNetworkDiagnostics();
  }
};

// ── 7. Model Switching ──────────────────────────────────────────
async function openSwitchModelModal() {
  openModal("switchModelModal");
  const list = document.getElementById("modelRadioList");
  list.innerHTML = `<div style="color:var(--text-muted); padding:10px;">Loading models...</div>`;

  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    list.innerHTML = "";

    (data.models || []).forEach(m => {
      const label = document.createElement("label");
      label.style.display = "flex";
      label.style.alignItems = "center";
      label.style.gap = "10px";
      label.style.padding = "8px 12px";
      label.style.border = "1px solid var(--border-subtle)";
      label.style.borderRadius = "6px";
      label.style.cursor = "pointer";

      const isCurrent = m.id === (dashboardData ? dashboardData.ai_engine.model_name : "");
      label.innerHTML = `
        <input type="radio" name="targetModelRadio" value="${m.id}" ${isCurrent ? 'checked' : ''} onchange="selectedNewModel='${m.id}'">
        <div>
          <b>${m.name || m.id}</b>
          <div style="font-size:0.75rem; color:var(--text-muted);">Size: ${m.size_gb || 0} GB | Format: ${m.format || 'Ollama'}</div>
        </div>
      `;
      list.appendChild(label);
    });
  } catch (e) {
    list.innerHTML = `<div style="color:var(--accent-red);">Failed to load models.</div>`;
  }
}

async function confirmSwitchModel() {
  if (!selectedNewModel) {
    closeModal("switchModelModal");
    return;
  }
  closeModal("switchModelModal");
  await fetch("/api/models/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: selectedNewModel })
  });
  refreshDashboard();
}

function reloadModel() {
  if (confirm("Reload current model in memory?")) {
    confirmSwitchModel();
  }
}

function openModal(id) {
  if (id === "switchModelModal") {
    openSwitchModelModal();
    return;
  }
  const el = document.getElementById(id);
  if (el) el.classList.add("active");
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("active");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
