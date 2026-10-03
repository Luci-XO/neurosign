/**
 * electron/preload.js
 * --------------------
 * Runs in a privileged context before the renderer's JS, with access to
 * both Node.js and the page's `window`. We use it only to expose one
 * constant (the backend's URL) to the renderer, via contextBridge - the
 * renderer itself has no direct Node access, which is the safer default.
 */

const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("neurosign", {
  apiBaseUrl: "http://127.0.0.1:5057",
});