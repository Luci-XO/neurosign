/**
 * renderer/js/neuro.js
 * Chat UI for Neuro. Uses api() and authHeader() from app.js (loaded first).
 */
(function () {
  const byId = (id) => document.getElementById(id);
  let chatHistory = []; // [{role: 'user'|'assistant', text: string}]
  let sending = false;

  function addMessage(role, text, pending = false) {
    const box = byId("neuro-messages");
    const div = document.createElement("div");
    div.className = "neuro-msg " + role + (pending ? " pending" : "");
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
  }

  async function send() {
    if (sending) return;
    const input = byId("neuro-input");
    const message = input.value.trim();
    if (!message) return;

    const errEl = byId("neuro-error");
    errEl.textContent = "";
    byId("neuro-offline-note").classList.add("hidden");

    addMessage("user", message);
    chatHistory.push({ role: "user", text: message });
    input.value = "";

    const pendingEl = addMessage("assistant", "Thinking...", true);
    sending = true;
    byId("neuro-send-btn").disabled = true;

    try {
      const r = await api("/api/neuro/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: chatHistory.slice(0, -1) }),
      });
      pendingEl.remove();
      addMessage("assistant", r.answer);
      chatHistory.push({ role: "assistant", text: r.answer });
      if (r.source === "offline") {
        byId("neuro-offline-note").classList.remove("hidden");
      }
    } catch (e) {
      pendingEl.remove();
      errEl.textContent = e.message;
    } finally {
      sending = false;
      byId("neuro-send-btn").disabled = false;
      input.focus();
    }
  }

  byId("neuro-send-btn").addEventListener("click", send);
  byId("neuro-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });

  // Reset the conversation each time Neuro is opened fresh (home -> Neuro).
  const origGoHome = window.NS_goHome;
  document.getElementById("home-neuro-btn").addEventListener("click", () => {
    // only reset if we're not already mid-conversation from a login redirect
  });
})();