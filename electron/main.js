/**
 * electron/main.js
 * Starts the Flask backend, waits until it answers /api/health, then opens the window.
 * On quit it kills the whole backend process tree so nothing keeps port 5057 busy.
 */
const { app, BrowserWindow, dialog, session } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn, spawnSync } = require("child_process");

const PROJECT_ROOT = path.join(__dirname, "..");
const BACKEND_DIR = path.join(PROJECT_ROOT, "backend");
const HEALTH_URL = "http://127.0.0.1:5057/api/health";

let mainWindow = null;
let backend = null;

function pythonPath() {
  const win = path.join(BACKEND_DIR, "venv", "Scripts", "python.exe");
  const posix = path.join(BACKEND_DIR, "venv", "bin", "python");
  if (fs.existsSync(win)) return win;
  if (fs.existsSync(posix)) return posix;
  console.warn("[main] backend/venv not found - falling back to system python");
  return "python";
}

function startBackend() {
  backend = spawn(pythonPath(), ["-u", "app.py"], {
    cwd: BACKEND_DIR,
    stdio: "inherit",
    env: { ...process.env, NEUROSIGN_DEBUG: "false" },
  });
  backend.on("error", (err) => console.error("[main] backend failed to start:", err));
  backend.on("exit", (code) => console.log("[main] backend exited with code", code));
}

function stopBackend() {
  if (!backend || backend.killed) return;
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(backend.pid), "/T", "/F"]);   // kill the whole tree
    } else {
      backend.kill();
    }
  } catch (e) {
    console.error("[main] could not stop backend:", e);
  }
  backend = null;
}

function healthOk() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, (res) => { res.resume(); resolve(res.statusCode === 200); });
    req.on("error", () => resolve(false));
    req.setTimeout(800, () => { req.destroy(); resolve(false); });
  });
}

async function waitForBackend(timeoutMs = 40000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await healthOk()) return true;
    if (backend === null || backend.exitCode !== null) return false;   // backend crashed
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200, height: 800, minWidth: 900, minHeight: 650, title: "NeuroSign",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(PROJECT_ROOT, "renderer", "index.html"));
  mainWindow.on("closed", () => { mainWindow = null; });
}

// Only one copy of the app at a time (a second copy would fight over port 5057).
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.whenReady().then(async () => {
    // Allow only microphone access.
    session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === "media"));

    startBackend();
    const ok = await waitForBackend();
    if (!ok) {
      dialog.showErrorBox(
        "NeuroSign backend did not start",
        "Check the terminal for Python errors.\nIs another copy still using port 5057?\n" +
        "(PowerShell: Get-NetTCPConnection -LocalPort 5057)"
      );
      stopBackend();
      app.quit();
      return;
    }
    createWindow();
    app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
  });

  app.on("window-all-closed", () => { stopBackend(); if (process.platform !== "darwin") app.quit(); });
  app.on("before-quit", stopBackend);
  process.on("exit", stopBackend);
}