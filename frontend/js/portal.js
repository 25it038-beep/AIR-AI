// AIR AI Portal Engine - Authentication & Connection Lifecycle
let requiresPin = false;
let isAuthenticated = false;

// Register Service Worker for PWA (Section 30)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(err => {
      console.debug("PWA service worker skipped:", err);
    });
  });
}

// ── Particle Canvas Animation ──────────────────────────────────
const canvas = document.getElementById("networkCanvas");
const ctx = canvas.getContext("2d");
let width, height, particles = [];
const particleCount = 38;

function resizeCanvas() {
  width = canvas.width = window.innerWidth;
  height = canvas.height = window.innerHeight;
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();

class Particle {
  constructor() {
    this.x = Math.random() * width;
    this.y = Math.random() * height;
    this.vx = (Math.random() - 0.5) * 0.5;
    this.vy = (Math.random() - 0.5) * 0.5;
    this.radius = Math.random() * 2 + 1;
  }
  update() {
    this.x += this.vx;
    this.y += this.vy;
    if (this.x < 0 || this.x > width) this.vx *= -1;
    if (this.y < 0 || this.y > height) this.vy *= -1;
  }
  draw() {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0, 242, 254, 0.65)";
    ctx.fill();
  }
}

for (let i = 0; i < particleCount; i++) {
  particles.push(new Particle());
}

function animateParticles() {
  ctx.clearRect(0, 0, width, height);
  for (let i = 0; i < particles.length; i++) {
    particles[i].update();
    particles[i].draw();
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 120) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(0, 242, 254, ${1 - dist / 120 * 0.75})`;
        ctx.lineWidth = 0.7;
        ctx.stroke();
      }
    }
  }
  requestAnimationFrame(animateParticles);
}
animateParticles();

// ── Auth & Status Verification ─────────────────────────────────
async function checkAuthAndStatus() {
  const token = localStorage.getItem("hs_token") || "";
  try {
    const res = await fetch("/api/auth/status", {
      headers: token ? { "Authorization": `Bearer ${token}` } : {}
    });
    if (res.ok) {
      const data = await res.json();
      requiresPin = data.require_pin;
      isAuthenticated = data.is_authenticated;

      const pinSec = document.getElementById("pinSection");
      const secVal = document.getElementById("securityStatusVal");

      if (requiresPin && !isAuthenticated) {
        pinSec.style.display = "block";
        secVal.innerHTML = `<span style="color:var(--accent-amber)">🔒 AUTH REQUIRED</span>`;
        document.getElementById("btnEnter").innerText = "CONNECT TO AIR AI ➔";
      } else {
        pinSec.style.display = "none";
        secVal.innerHTML = `● SECURE SESSION`;
        const btn = document.getElementById("btnEnter");
        if (btn) btn.innerText = "ENTERING AIR AI ➔";
        setTimeout(() => {
          window.location.replace("/chat");
        }, 400);
      }
    }
  } catch (e) {
    console.debug("Auth status check failed:", e);
  }

  // Model & Network Status
  try {
    const res2 = await fetch("/api/status");
    if (res2.ok) {
      const s = await res2.json();
      if (s.model && s.model.name) {
        document.getElementById("modelStatusText").innerText = s.model.name.replace(":latest", "");
      }
      if (s.network && s.network.host_ip) {
        const ipEl = document.getElementById("modalHostIp");
        if (ipEl) ipEl.innerText = s.network.host_ip;
      }
    }
  } catch (e) {}
}

window.addEventListener("DOMContentLoaded", () => {
  checkAuthAndStatus();
});

function handlePinKeyDown(e) {
  if (e.key === "Enter") {
    handleEnterClick();
  }
}

async function handleEnterClick() {
  const pinInput = document.getElementById("inputPin");
  const pinError = document.getElementById("pinError");
  if (pinError) pinError.style.display = "none";

  if (requiresPin && !isAuthenticated) {
    const pinVal = pinInput ? pinInput.value.trim() : "";
    if (pinVal.length < 4) {
      if (pinError) {
        pinError.innerText = "Please enter the 6-digit access PIN.";
        pinError.style.display = "block";
      }
      return;
    }

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pinVal })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        if (pinError) {
          pinError.innerText = data.detail || "Invalid or expired PIN.";
          pinError.style.display = "block";
        }
        return;
      }

      // Store authenticated token
      localStorage.setItem("hs_token", data.token);
      isAuthenticated = true;
    } catch (e) {
      if (pinError) {
        pinError.innerText = "Connection error. Is AIR AI Host running?";
        pinError.style.display = "block";
      }
      return;
    }
  }

  // Direct to AI Chat immediately
  window.location.href = "/chat";
}

async function runConnectionSequence() {
  window.location.href = "/chat";
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("active");
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("active");
}
