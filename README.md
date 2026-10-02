# AIR AI Network ⚡
### Portable Offline AI Appliance for Any Device · Zero Internet Required

**AIR AI** transforms any Windows laptop into a standalone, air-gapped, offline AI server appliance running directly from a portable USB drive. By leveraging the host laptop's Windows Mobile Hotspot and local GPU/CPU compute, any smartphone, tablet, laptop, or PC connecting to the Wi-Fi gets instant, private, offline access to high-performance AI models through their standard web browser—**zero Internet connection or app installation required**.

```text
       ┌────────────────────────────────────────────────────────┐
       │                 AIR AI USB Flash Drive                 │
       │   (Portable Runtime · Pre-configured Offline Models)   │
       └───────────────────────────┬────────────────────────────┘
                                   │ Plug into USB Port
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                  Windows Host Laptop                   │
       │   AIR-AI.bat → Scoped Firewall → Local Inference       │
       └───────────────────────────┬────────────────────────────┘
                                   │ Creates Local Wi-Fi
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                 Windows Mobile Hotspot                 │
       │             (Default IP: 192.168.137.1)                │
       └───────────────────────────┬────────────────────────────┘
                                   │ Connect via Wi-Fi
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │       Connected Devices (Any Phone, Tablet, PC)        │
       │     Samsung · Realme · iPhone · iPad · OnePlus · Mi    │
       └───────────────────────────┬────────────────────────────┘
                                   │ Auto Captive Portal Trigger
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                  AIR AI Chat Interface                 │
       │      http://192.168.137.1/  ·  http://air-ai.local      │
       │   (Real-time Token Streaming via WebSocket / SSE)      │
       └────────────────────────────────────────────────────────┘
```

> **Attribution:** All rights reserved hs solution : https://hs-ai-studio.onrender.com/

---

## 🚀 Key Features

* **100% Offline & Private:** Operates completely air-gapped with no cloud dependencies, no external telemetry, and zero tracking. Your prompts never leave your local hotspot.
* **Universal Device Compatibility:** Responsive interface optimized for all screen sizes—Android (Samsung, Realme, OnePlus, Xiaomi, Pixel), iOS (iPhone, iPad), Windows, macOS, and Linux.
* **Instant Captive Portal Auto-Redirection:**
  * Serves the full AIR AI Chat UI directly on `GET /` (`HTTP 200 OK`), eliminating redirect loops.
  * Intercepts vendor probes:
    * **Android / AOSP:** `/generate_204`, `/gen_204`
    * **Realme / Oppo / OnePlus (ColorOS & AllawnOS):** `/generate204`, `/gen204`, `/check_network_status.txt`
    * **Samsung:** `/mobile/status.php`, `/wifi/status`
    * **Apple CNA (iOS/macOS):** `/hotspot-detect.html`, `/library/test/success.html`, `/bag`
    * **Windows NCSI:** `/connecttest.txt`, `/ncsi.txt`
    * **Xiaomi / MIUI / HyperOS:** `/ptlogin/status`, `/connect.rom.miui.com`
    * **RFC 8908 / RFC 8910:** `/.well-known/captive-portal`
* **Automated USB Downloader Included:** Interactive model downloader script located in `AI Dwonload for windows/` allows you to pick preset models (Gemma 2, Llama 3.2, Qwen 3.5, Dolphin, Heretic) or download any custom HuggingFace GGUF model directly onto your USB drive.
* **Portable USB Architecture:** Dynamically detects drive letters (`D:`, `E:`, `F:`, `G:`, etc.)—never relies on hard-coded filesystem paths.
* **Hardware & VRAM Sensing:** Inspects CPU cores, RAM, discrete NVIDIA GPU, and VRAM to automatically select and configure the best compatible local model.
* **Multi-Client Concurrency Queue:** Protects GPU memory by managing a request semaphore, enabling multiple devices to chat smoothly without memory exhaustion.
* **Real-time Live Telemetry:** Host admin dashboard (`/dashboard`) shows live CPU %, RAM %, GPU %, VRAM %, active connected devices, and device blocking controls.

---

## 💾 How to Download and Setup AIR AI on a USB Drive

Follow these step-by-step instructions to create a self-contained AIR AI USB drive.

### Prerequisites & Recommendations
* **USB Drive:** Minimum **16 GB** (32 GB or 64 GB recommended for multiple models).
* **Filesystem:** Format the USB drive as **NTFS** or **exFAT** (do **NOT** use FAT32, as FAT32 cannot store single files larger than 4 GB, which causes large AI models to fail).
* **Host PC:** A Windows 10/11 laptop or desktop with Internet access for the initial download step only.

---

### Step 1: Copy AIR AI Files to the USB Drive
1. Insert your formatted USB drive into your Windows PC.
2. Copy the entire `hs AI` project directory onto your USB drive (you can copy it to the root of the USB drive, e.g. `E:\`).
3. Ensure the folder structure matches the **Project Directory Structure** shown below.

---

### Step 2: Download the AI Models onto the USB Drive
The project includes a built-in automated installer and model downloader.

1. Open your USB drive in Windows File Explorer.
2. Navigate to the **`AI Dwonload for windows`** directory:
   ```text
   E:\AI Dwonload for windows\
   ```
3. Double-click **`install.bat`** (or open PowerShell and run `install-core.ps1`).
4. The interactive installer will display your available USB storage and the **Model Catalog**:
   ```text
   [1] Gemma 2 2B Abliterated (~1.6 GB) [UNCENSORED] - BLAZING FAST (Recommended)
   [2] Gemma 4 E4B Ultra Uncensored Heretic (~5.3 GB) [UNCENSORED]
   [3] Qwen 3.5 9B Uncensored Aggressive (~5.2 GB) [UNCENSORED]
   [4] NemoMix Unleashed 12B (~7.0 GB) [UNCENSORED] - HEAVYWEIGHT
   [5] Dolphin 2.9 Llama 3 8B (~4.9 GB) [UNCENSORED]
   [6] Llama 3.2 3B Instruct (~2.0 GB) [STANDARD] - FAST & BALANCED
   [C] CUSTOM - Enter your own HuggingFace GGUF URL
   ```
5. **Choose your model(s):**
   * Enter `1` for the lightweight, ultra-fast model (runs on almost any laptop CPU/GPU).
   * Enter comma-separated numbers (e.g. `1,6`) to install multiple models.
   * Enter `c` to paste a direct link to any GGUF model from [HuggingFace](https://huggingface.co/).
6. The installer will automatically:
   * Download the selected GGUF model weights into `Shared/models/` and `models/`.
   * Verify file sizes and download integrity.
   * Set up local runtime engine binaries in `Shared/bin/` if needed.
   * Generate model configuration profiles.
7. Once the installer displays **`SETUP COMPLETE!`**, your USB drive is completely ready for offline use!

---

### Step 3: Verify Offline Readiness
* Eject your USB drive or disconnect the PC from the Internet.
* Your USB drive is now an independent, air-gapped AI appliance ready to run anywhere.

---

## 📂 Project Directory Structure

```text
AIR-AI/
├── AIR-AI.bat                    # Elevated one-click launcher (configures firewall & starts AIR AI)
├── HS-AI.bat                     # Fallback batch launcher with UAC auto-elevation
├── HS-AI.exe                     # Compiled standalone executable launcher
├── HS-AI.py                      # Python root launcher
├── HS-AI.spec                    # PyInstaller packaging specification
│
├── AI Dwonload for windows/      # Automated USB Model Downloader
│   ├── install.bat               # Interactive USB installer script for Windows
│   ├── install-core.ps1          # Core PowerShell downloader with model catalog & GGUF support
│   └── config/                   # Downloader configuration
│
├── Windows/                      # Windows platform management & scripts
│   ├── install.bat               # Windows installer wrapper
│   ├── install-core.ps1          # Windows setup pipeline
│   ├── start-fast-chat.bat       # Fast standalone chat launch script
│   ├── uninstall.bat             # Clean uninstaller wrapper
│   └── uninstall-core.ps1        # Uninstaller PowerShell script
│
├── Android/                      # Android documentation and client utilities
├── Mac/                          # macOS client instructions
├── Linux/                        # Linux client instructions
│
├── launcher/                     # Host hardware & environment detection
│   ├── hardware_detector.py      # Detects CPU, RAM, discrete GPU, VRAM, and OS
│   ├── model_scanner.py          # Matches hardware capabilities against model requirements
│   └── startup_banner.py         # Terminal ASCII status banner & startup box
│
├── server/                       # Core FastAPI application & services
│   ├── main.py                   # Main server entry, middleware & route definitions
│   ├── logger_setup.py           # Structured logging across subsystems
│   ├── api/                      # REST API endpoints
│   │   ├── captive_portal.py     # Captive portal diagnostic endpoints
│   │   ├── chat.py               # Chat completion & streaming endpoint
│   │   ├── models.py             # Model discovery, status, and loading
│   │   ├── devices.py            # Device listing, tracking, and blocking
│   │   ├── network.py            # Hotspot and network management
│   │   ├── status.py             # Hardware telemetry API
│   │   ├── security.py           # Authentication & PIN validation
│   │   └── files.py              # File and image upload handlers
│   ├── websocket/
│   │   └── chat_ws.py            # Low-latency WebSocket chat stream
│   ├── model_manager/
│   │   ├── manager.py            # ModelManager lifecycle controller
│   │   ├── request_queue.py      # Multi-client concurrency & semaphore queue
│   │   └── adapters/             # Model engine runtime adapters
│   ├── device_manager/
│   │   └── device_tracker.py     # Discovers and tracks connected client devices
│   ├── network_manager/
│   │   ├── host_ip.py            # Auto-detects Mobile Hotspot IP (192.168.137.1)
│   │   ├── hotspot.py            # Hotspot status detector & controller
│   │   ├── mdns.py               # Multicast DNS service for air-ai.local
│   │   └── qr.py                 # Terminal & web QR code generator
│   └── security/
│       ├── auth.py               # Session tokens & optional PIN manager
│       ├── rate_limiter.py       # Sliding-window rate limiter per client IP
│       ├── firewall.py           # IP blocking & max client capacity
│       └── sanitizer.py          # Input & path traversal protection
│
├── network/                      # Captive Portal & Network Appliance Subsystem
│   ├── captive_portal/
│   │   ├── endpoints.py          # Multi-brand probe routes (Android, Apple, Windows, Samsung, Xiaomi)
│   │   ├── server.py             # Dedicated Port 80 proxy server
│   │   ├── dns.py                # Captive DNS interceptor
│   │   ├── detector.py           # User-Agent client classification
│   │   └── diagnostics.py        # Captive portal self-check
│   ├── dns_server.py             # Local RFC 1035 UDP 53 DNS server
│   ├── hotspot_detector.py       # Windows Mobile Hotspot adapter detection
│   ├── firewall_checker.py       # Scoped Windows Firewall rule generator
│   └── port_manager.py           # Port availability checker (Ports 80, 53, 8000)
│
├── frontend/                     # Modern Web Client (HTML5 / PWA)
│   ├── chat.html                 # Full responsive AIR AI Chat interface
│   ├── portal.html               # Captive Portal landing page
│   ├── dashboard.html            # Host Admin Dashboard with live telemetry gauges
│   ├── manifest.json             # Progressive Web App manifest
│   ├── sw.js                     # Offline Service Worker
│   ├── css/                      # Stylesheets (glassmorphic dark UI, mobile drawer)
│   └── js/                       # Client JavaScript (chat.js, portal.js, dashboard.js)
│
├── models/                       # Model Storage & Registry
│   ├── registry.json             # Curated model catalog metadata & specifications
│   ├── text/                     # Text LLMs (Llama 3.2, Gemma 2, etc.)
│   ├── vision/                   # Vision models (Qwen 3 VL, etc.)
│   ├── embedding/                # Embedding models
│   └── speech/                   # Audio / Speech models
│
├── Shared/                       # Shared Assets & Runtimes
│   ├── bin/                      # Offline inference engine binaries
│   ├── config/                   # Shared model configurations
│   ├── models/                   # Downloaded GGUF weights
│   └── vendor/                   # Offline JavaScript libraries (highlight.js, marked.js)
│
├── scripts/                      # System & Network Setup Utilities
│   ├── airai_network_setup.bat   # Complete Windows firewall, hosts, and DNS setup
│   ├── fix_network_access.bat    # Inbound firewall rule generator
│   └── restore_network_defaults.bat # Resets network rules to system defaults
│
├── config/
│   └── config.json               # Server configuration, ports, PIN settings, and limits
├── data/
│   ├── chats.json                # Persisted chat conversations
│   └── devices.json              # Discovered and tracked client devices
├── logs/                         # Detailed subsystem runtime logs
└── tests/                        # 100% automated test suite (33/33 tests)
```

---

## ⚡ How to Run AIR AI

### 1. Enable Windows Mobile Hotspot
1. On your Windows laptop, open **Settings** (`Win + I`).
2. Go to **Network & internet** $\rightarrow$ **Mobile hotspot**.
3. Toggle **Mobile hotspot** to **ON**.
4. Set your desired Network Name (SSID) and Password.

### 2. Launch AIR AI
1. Right-click **`AIR-AI.bat`** (or `HS-AI.bat`) and choose **Run as administrator**.
   *(If double-clicked, the script will automatically prompt for UAC administrator permission).*
2. The launcher automatically:
   * Adds scoped Windows Firewall rules for Ports `80`, `8000` (TCP), and `53` (UDP) across all profiles.
   * Maps probe domains (`connectivitycheck.gstatic.com`, etc.) to the local hotspot IP.
   * Verifies hardware profile (CPU, RAM, GPU, VRAM) and model availability.
   * Starts the local inference engine and the dedicated Port 80 captive portal server.
   * Displays the **AIR AI READY** status banner with host IP and QR code.

### 3. Connect Other Devices
1. On your phone, tablet, or secondary laptop, turn on Wi-Fi and connect to the Mobile Hotspot network.
2. **Instant Redirection:**
   * Most devices will automatically pop up a **"Sign in to network"** or captive notification that opens the **AIR AI Chat** immediately.
   * Alternatively, open any browser on the device and visit:
     ```text
     http://192.168.137.1/
     ```
     or
     ```text
     http://air-ai.local:8000/
     ```
   * Or simply scan the **QR code** shown on the laptop's terminal or Host Dashboard!

---

## 🛡️ Host Administration & Telemetry Dashboard

Access the host management dashboard directly on the host laptop:
```text
http://localhost:8000/dashboard
```
or from any connected device:
```text
http://192.168.137.1:8000/dashboard
```

* **Live Hardware Telemetry:** Real-time gauges for CPU utilization, RAM usage, GPU load, and VRAM consumption.
* **Connected Device Tracker:** See device types (Phone, Tablet, PC), operating systems, IP addresses, connection durations, and request counts.
* **Firewall Controls:** One-click block/unblock any client IP address.
* **Active Model Control:** Switch active models or adjust concurrency limits on the fly.
* **Optional PIN Security:** Enable PIN authentication in `config/config.json` to require client devices to enter a 4-digit code before chatting.

---

## 🧪 Testing & Verification

Run the comprehensive 33-test automated test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

The test suite validates:
* Hardware detection (CPU cores, RAM, NVIDIA GPU, VRAM, Windows version).
* Model registry specifications, RAM/VRAM checks, and model hot-swapping.
* Captive portal probes across Android (`/generate_204`, `/generate204`), Apple (`/hotspot-detect.html`), Windows (`/ncsi.txt`), and direct root (`GET /`) rendering.
* Device tracking, firewall IP blocking, and sliding-window rate limiting.
* End-to-end inference token streaming with the local AI engine.

---

## 📜 Brand & Attribution

* **Project:** AIR AI Network
* **Subtitle:** Portable Local Intelligence Network Appliance
* **Rights:** All rights reserved hs solution : https://hs-ai-studio.onrender.com/
