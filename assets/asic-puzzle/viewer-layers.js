async function loadLayers() {
  const response = await fetch(document.body.dataset.scene);
  if (!response.ok) throw new Error(`Layer request failed: ${response.status}`);
  const data = await new Response(response.body.pipeThrough(new DecompressionStream("gzip"))).json();
  const bounds = data.bounds;
  const canvas = document.getElementById("layer-canvas");
  canvas.style.aspectRatio = `${bounds[3] - bounds[1]} / ${bounds[2] - bounds[0]}`;
  const ctx = canvas.getContext("2d");
  const hitContext = document.createElement("canvas").getContext("2d");
  const legend = document.getElementById("layer-legend");
  const layers = data.layers.map((layer, index) => {
    const path = new Path2D();
    let offset = 0;
    for (const count of layer.counts) {
      const points = layer.vertices.slice(offset, offset + count * 2);
      let area = 0;
      for (let i = 0; i < count; i++) {
        const next = (i + 1) % count;
        area += points[2 * i] * points[2 * next + 1] - points[2 * next] * points[2 * i + 1];
      }
      // Consistent winding lets overlapping polygons share a single filled path.
      for (let i = 0; i < count; i++) {
        const j = area < 0 ? count - 1 - i : i;
        if (i === 0) path.moveTo(points[2 * j], points[2 * j + 1]);
        else path.lineTo(points[2 * j], points[2 * j + 1]);
      }
      path.closePath();
      offset += count * 2;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = layer.name;
    button.dataset.layer = layer.name;
    button.style.setProperty("--layer-color", layer.color);
    button.setAttribute("aria-label", `Highlight ${layer.name} layer`);
    button.addEventListener("pointerenter", () => { hovered = index; highlight(); });
    button.addEventListener("pointerleave", () => { hovered = null; highlight(); });
    button.addEventListener("focus", () => { focused = index; highlight(); });
    button.addEventListener("blur", () => { focused = null; highlight(); });
    legend.prepend(button);
    return {name: layer.name, color: layer.color, opacity: layer.opacity, path, button};
  });
  let hovered = null, focused = null, selected = null, transform;
  const draw = () => {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(...transform);
    layers.forEach((layer, index) => {
      ctx.fillStyle = layer.color;
      ctx.globalAlpha = selected === null ? layer.opacity : selected === index ? 1 : .035;
      ctx.fill(layer.path);
    });
    ctx.globalAlpha = 1;
  };
  const highlight = () => {
    selected = hovered ?? focused;
    document.body.dataset.highlightedLayer = selected === null ? "" : layers[selected].name;
    layers.forEach((layer, index) => {
      layer.button.classList.toggle("is-active", selected === index);
      layer.button.classList.toggle("is-muted", selected !== null && selected !== index);
    });
    draw();
  };
  const resize = new ResizeObserver(() => {
    const ratio = Math.min(devicePixelRatio, 2);
    const width = Math.round(canvas.clientWidth * ratio), height = Math.round(canvas.clientHeight * ratio);
    if (!width || !height) return;
    canvas.width = width;
    canvas.height = height;
    const [x0, y0, x1, y1] = bounds;
    const padding = 12 * ratio;
    const scale = Math.min((width - padding * 2) / (y1 - y0), (height - padding * 2) / (x1 - x0));
    transform = [0, scale, scale, 0, (width - (y1 - y0) * scale) / 2 - y0 * scale,
      (height - (x1 - x0) * scale) / 2 - x0 * scale];
    highlight();
    document.getElementById("scene-status")?.remove();
  });
  resize.observe(canvas);
  let pointer = null, pending = false;
  canvas.addEventListener("pointermove", event => {
    pointer = [event.clientX, event.clientY];
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      if (!pointer || !transform) return;
      const rect = canvas.getBoundingClientRect();
      const x = ((pointer[1] - rect.top) * canvas.height / rect.height - transform[5]) / transform[1];
      const y = ((pointer[0] - rect.left) * canvas.width / rect.width - transform[4]) / transform[2];
      const index = layers.findLastIndex(layer => hitContext.isPointInPath(layer.path, x, y));
      const picked = index < 0 ? null : index;
      if (picked !== hovered) { hovered = picked; highlight(); }
    });
  });
  canvas.addEventListener("pointerleave", () => { pointer = null; hovered = null; highlight(); });
  window.addEventListener("pagehide", event => { if (!event.persisted) resize.disconnect(); });
}

loadLayers().catch(error => {
  document.getElementById("scene-status").textContent = "The conducting layers could not load. Please reload the figure.";
  console.error(error);
});
