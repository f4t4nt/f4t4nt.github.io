(() => {
  const systemTheme = matchMedia("(prefers-color-scheme: dark)");
  const updateFigures = () => {
    const selected = document.documentElement.dataset.theme;
    const dark = selected ? selected === "dark" : systemTheme.matches;
    document.querySelectorAll("img[data-dark-src]").forEach(img => {
      img.src = dark ? img.dataset.darkSrc : img.dataset.lightSrc;
    });
  };
  new MutationObserver(updateFigures).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
  systemTheme.addEventListener("change", updateFigures);
  updateFigures();
  document.addEventListener("contextmenu", event => {
    if (event.target.closest("figure img")) event.preventDefault();
  });
  document.querySelectorAll("iframe[data-src]").forEach(frame => {
    frame.src = frame.dataset.src;
  });
  const codeCells = [...document.querySelectorAll("details.code")];
  const expandControls = [...document.querySelectorAll(".expand-code")];
  const updateCodeControl = () => {
    codeCells.forEach(cell => {
      const label = cell.querySelector(".code-label");
      label.textContent = `${cell.open ? "Hide" : "View"} ${label.dataset.subject}`;
    });
    const label = codeCells.every(cell => cell.open) ? "Collapse all code" : "Expand all code";
    expandControls.forEach(control => { control.textContent = label; });
  };
  expandControls.forEach(control => control.addEventListener("click", () => {
    const top = control.getBoundingClientRect().top;
    const open = !codeCells.every(cell => cell.open);
    codeCells.forEach(cell => { cell.open = open; });
    updateCodeControl();
    requestAnimationFrame(() => window.scrollBy(0, control.getBoundingClientRect().top - top));
  }));
  codeCells.forEach(cell => cell.addEventListener("toggle", updateCodeControl));

  const links = [...document.querySelectorAll(".contents li a")];
  const headings = links.map(link => document.querySelector(link.hash));
  let pending = false;
  const markSection = () => {
    let current = -1;
    headings.forEach((heading, index) => {
      if (heading.getBoundingClientRect().top < 180) current = index;
    });
    links.forEach((link, index) => {
      if (index === current) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    pending = false;
  };
  const scheduleSectionUpdate = () => {
    if (!pending) { pending = true; requestAnimationFrame(markSection); }
  };
  document.addEventListener("scroll", scheduleSectionUpdate, {passive: true});
  window.addEventListener("resize", scheduleSectionUpdate);
  document.fonts.ready.then(scheduleSectionUpdate);
  markSection();
})();
