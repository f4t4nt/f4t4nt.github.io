(() => {
  const root = document.documentElement;
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") root.dataset.theme = saved;
  } catch {}

  document.addEventListener("DOMContentLoaded", () => {
    const buttons = [...document.querySelectorAll(".theme-toggle")];
    if (!buttons.length) return;
    const isDark = () => root.dataset.theme
      ? root.dataset.theme === "dark"
      : systemTheme.matches;
    const updateButton = () => {
      const label = isDark() ? "Switch to light mode" : "Switch to dark mode";
      buttons.forEach(button => {
        button.setAttribute("aria-label", label);
        button.title = label;
        button.dataset.dark = String(isDark());
      });
    };
    buttons.forEach(button => button.addEventListener("click", () => {
      root.dataset.theme = isDark() ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch {}
      updateButton();
    }));
    systemTheme.addEventListener("change", updateButton);
    updateButton();
    buttons.forEach(button => { button.hidden = false; });
  });
})();
