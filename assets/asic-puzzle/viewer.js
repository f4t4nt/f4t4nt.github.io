(() => {
  document.addEventListener("contextmenu", event => {
    if (event.target.closest("canvas, svg")) event.preventDefault();
  });
  const systemTheme = matchMedia("(prefers-color-scheme: dark)");
  const updateTheme = () => {
    let selected;
    try {
      selected = (window.parent !== window && window.parent.document.documentElement.dataset.theme) || localStorage.getItem("theme");
    } catch {}
    const dark = selected ? selected === "dark" : systemTheme.matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    window.dispatchEvent(new Event("asic-theme-change"));
  };
  systemTheme.addEventListener("change", updateTheme);
  try {
    if (window.parent !== window) new MutationObserver(updateTheme).observe(
      window.parent.document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
  } catch {}
  updateTheme();
  window.showInputBits = (container, text) => {
    const parts = text.split(/\[([01])\]/);
    container.replaceChildren(...parts.map((part, index) => {
      if (index % 2 === 0) return document.createTextNode(part);
      const bit = document.createElement("strong");
      bit.className = "active-bit";
      bit.textContent = part;
      bit.title = "Bit at the input on this edge";
      return bit;
    }));
    const active = container.querySelector(".active-bit");
    if (active && container.scrollWidth > container.clientWidth) {
      const bit = active.getBoundingClientRect(), box = container.getBoundingClientRect();
      if (bit.left < box.left || bit.right > box.right) {
        container.scrollLeft += (bit.left + bit.right - box.left - box.right) / 2;
      }
    }
  };
  window.createPlayback = (container, frameCount, showFrame) => {
    const intervalMs = 250;
    container.classList.add("playback-controls");
    const play = document.createElement("button");
    play.type = "button";
    play.className = "play-toggle";
    const buttons = document.createElement("div");
    buttons.className = "playback-buttons";
    const step = direction => {
      const button = document.createElement("button");
      button.type = "button";
      const label = direction < 0 ? "Step backward" : "Step forward";
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-keyshortcuts", direction < 0 ? "ArrowLeft" : "ArrowRight");
      button.title = label;
      button.innerHTML = `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="${direction < 0 ? "M3 3h1.5v10H3z M12 3v10L5 8z" : "M11.5 3H13v10h-1.5z M4 3l7 5-7 5z"}"/></svg>`;
      button.addEventListener("click", () => stepFrame(direction));
      return button;
    };
    const backward = step(-1), forward = step(1);
    buttons.append(backward, play, forward);
    const speed = document.createElement("select");
    speed.setAttribute("aria-label", "Playback speed");
    speed.title = "Playback speed";
    for (const rate of [.5, 1, 2]) speed.add(new Option(`${rate}×`, rate, rate === 1, rate === 1));
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = 0;
    slider.max = frameCount - 1;
    slider.value = 0;
    slider.setAttribute("aria-label", "Simulation frame");
    const position = document.createElement("output");
    let frame = 0, timer;
    const update = () => {
      play.textContent = timer ? "Pause" : frame === frameCount - 1 ? "Replay" : "Play";
      play.setAttribute("aria-label", `${play.textContent} simulation`);
      slider.value = frame;
      slider.style.setProperty("--progress", `${100 * frame / Math.max(1, frameCount - 1)}%`);
      slider.setAttribute("aria-valuetext", `Frame ${frame + 1} of ${frameCount}`);
      position.textContent = `${frame + 1} / ${frameCount}`;
      backward.disabled = frame === 0;
      forward.disabled = frame === frameCount - 1;
    };
    const pause = () => { clearInterval(timer); timer = undefined; update(); };
    const stepFrame = direction => {
      frame = Math.max(0, Math.min(frameCount - 1, frame + direction));
      pause();
      showFrame(frame);
    };
    document.addEventListener("keydown", event => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.isComposing) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (event.target.isContentEditable || event.target.closest('textarea, select, input:not([type="range"])')) return;
      event.preventDefault();
      stepFrame(event.key === "ArrowLeft" ? -1 : 1);
    });
    const start = () => {
      timer = setInterval(() => {
        showFrame(++frame);
        if (frame === frameCount - 1) pause();
        else update();
      }, intervalMs / Number(speed.value));
    };
    play.addEventListener("click", () => {
      if (timer) { pause(); return; }
      if (frame === frameCount - 1) { frame = 0; showFrame(frame); }
      start();
      update();
    });
    speed.addEventListener("change", () => {
      if (timer) { clearInterval(timer); start(); }
    });
    slider.addEventListener("input", () => {
      frame = Number(slider.value);
      pause();
      showFrame(frame);
    });
    window.addEventListener("pagehide", pause);
    container.append(buttons, slider, position, speed);
    update();
    showFrame(frame);
    return count => {
      pause();
      frameCount = count;
      frame = 0;
      slider.max = count - 1;
      update();
      showFrame(frame);
    };
  };
})();
