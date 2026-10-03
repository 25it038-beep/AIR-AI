# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['HS-AI.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend', 'frontend'), ('config', 'config'), ('scripts', 'scripts')],
    hiddenimports=[
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'websockets', 'psutil', 'pydantic', 'zeroconf',
        'network', 'network.captive_portal', 'network.captive_portal.server',
        'network.captive_portal.endpoints', 'network.captive_portal.detector',
        'network.captive_portal.dns', 'network.captive_portal.diagnostics',
        'server', 'server.web_search', 'server.main', 'server.api',
        'server.api.chat', 'server.api.models_api', 'server.api.system',
        'server.api.security_api', 'server.api.files', 'server.websocket',
        'server.websocket.chat_ws', 'server.websocket.metrics_ws'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HS-AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
)
