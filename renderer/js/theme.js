/**
 * renderer/js/theme.js
 * Dark/light toggle. Independent of login. Persisted in localStorage.
 * The <head> inline script in index.html already applies the saved theme
 * before paint - this file just wires up the button and keeps it in sync.
 */
(function () {
  const btn = document.getElementById("theme-toggle-btn");

  function apply(theme) {
    if (theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
      btn.textContent = "Light";
    } else {
      document.documentElement.removeAttribute("data-theme");
      btn.textContent = "Dark";
    }
    localStorage.setItem("neurosign_theme", theme);
  }

  const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  apply(current); // sync the button label with whatever the head script already applied

  btn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    apply(next);
  });
})();