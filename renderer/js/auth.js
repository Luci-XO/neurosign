/**
 * renderer/js/auth.js
 * Sign in / sign up / forgot-password screen. Loaded after app.js so it can call
 * window.NS_onLogin() / window.NS_goHome() once authenticated or cancelled.
 */
(function () {
  const API = window.neurosign.apiBaseUrl;
  const byId = (id) => document.getElementById(id);

  let mode = "login"; // or "signup"

  function setError(el, msg) {
    el.textContent = msg || "";
  }

  async function post(path, body) {
    let res;
    try {
      res = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (e) {
      throw new Error("Cannot reach the NeuroSign backend. Please restart the app.");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  function applyMode() {
    byId("auth-title").textContent = mode === "login" ? "Sign in to NeuroSign" : "Create your account";
    byId("auth-submit").textContent = mode === "login" ? "Sign in" : "Sign up";
    byId("consent-field").classList.toggle("hidden", mode !== "signup");
    byId("auth-toggle-mode").textContent = mode === "login" ? "Need an account? Sign up" : "Already have an account? Sign in";
    setError(byId("auth-error"), "");
  }

  byId("login-back-home").addEventListener("click", () => {
    window.NS_goHome();
  });

  byId("auth-toggle-mode").addEventListener("click", (e) => {
    e.preventDefault();
    mode = mode === "login" ? "signup" : "login";
    applyMode();
  });

  byId("auth-submit").addEventListener("click", async () => {
    const username = byId("auth-username").value.trim();
    const password = byId("auth-password").value;
    const err = byId("auth-error");
    setError(err, "");

    if (!username || !password) return setError(err, "Please enter a username and password.");

    const btn = byId("auth-submit");
    btn.disabled = true;
    try {
      if (mode === "login") {
        const r = await post("/api/auth/login", { username, password });
        localStorage.setItem("neurosign_token", r.token);
        localStorage.setItem("neurosign_username", r.username);
        window.NS_onLogin(r.token, r.username);
      } else {
        const consent = byId("auth-consent").checked;
        if (!consent) { btn.disabled = false; return setError(err, "Please agree to the data notice to continue."); }
        const r = await post("/api/auth/register", { username, password, consent });
        byId("recovery-code-value").textContent = r.recovery_code;
        byId("auth-main-card").classList.add("hidden");
        byId("recovery-card").classList.remove("hidden");
        byId("recovery-card").dataset.username = username;
        byId("recovery-card").dataset.password = password;
      }
    } catch (e) {
      setError(err, e.message);
    } finally {
      btn.disabled = false;
    }
  });

  byId("recovery-continue").addEventListener("click", async () => {
    const username = byId("recovery-card").dataset.username;
    const password = byId("recovery-card").dataset.password;
    byId("recovery-card").classList.add("hidden");
    byId("auth-main-card").classList.remove("hidden");
    mode = "login";
    applyMode();
    try {
      const r = await post("/api/auth/login", { username, password });
      localStorage.setItem("neurosign_token", r.token);
      localStorage.setItem("neurosign_username", r.username);
      window.NS_onLogin(r.token, r.username);
    } catch (e) {
      setError(byId("auth-error"), "Account created. Please sign in.");
    }
  });

  byId("auth-forgot").addEventListener("click", (e) => {
    e.preventDefault();
    byId("auth-main-card").classList.add("hidden");
    byId("forgot-card").classList.remove("hidden");
    setError(byId("forgot-error"), "");
  });

  byId("forgot-cancel").addEventListener("click", () => {
    byId("forgot-card").classList.add("hidden");
    byId("auth-main-card").classList.remove("hidden");
  });

  byId("forgot-submit").addEventListener("click", async () => {
    const username = byId("forgot-username").value.trim();
    const recovery_code = byId("forgot-code").value.trim();
    const new_password = byId("forgot-new-password").value;
    const err = byId("forgot-error");
    setError(err, "");
    if (!username || !recovery_code || !new_password) return setError(err, "Please fill in every field.");
    const btn = byId("forgot-submit");
    btn.disabled = true;
    try {
      await post("/api/auth/reset-password", { username, recovery_code, new_password });
      byId("forgot-card").classList.add("hidden");
      byId("auth-main-card").classList.remove("hidden");
      mode = "login";
      applyMode();
      setError(byId("auth-error"), "Password changed. Please sign in.");
    } catch (e) {
      setError(err, e.message);
    } finally {
      btn.disabled = false;
    }
  });

  [byId("auth-username"), byId("auth-password")].forEach((input) => {
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") byId("auth-submit").click(); });
  });

  window.NS_showLoginMessage = function (msg) {
    setError(byId("auth-error"), msg);
  };

  applyMode();
  const savedToken = localStorage.getItem("neurosign_token");
  const savedUsername = localStorage.getItem("neurosign_username");
  if (savedToken && savedUsername) {
    window.NS_onLogin(savedToken, savedUsername);
  }
})();