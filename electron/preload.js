/**
 * electron/preload.js
 * --------------------
 * Runs in a privileged context before the renderer's JS. Exposes the backend's
 * URL and one safe Node capability (opening a link in the system's default
 * browser) to the renderer via contextBridge - the renderer itself has no
 * direct Node access, which is the safer default.
 */

const { contextBridge, shell } = require("electron");

contextBridge.exposeInMainWorld("neurosign", {
  apiBaseUrl: "http://127.0.0.1:5057",
  openExternal: (url) => shell.openExternal(url),
});