import * as THREE from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";
import {ViewportGizmo} from "three-viewport-gizmo";

function simulateWarmup(model, a, b) {
  const values = new Uint8Array(model.nets);
  const settle = inputs => {
    for (const [pin, value] of Object.entries(inputs)) values[model.ports[pin]] = value;
    for (const [net, inputs, table] of model.gates) {
      const index = inputs.reduce((index, input, bit) => index | values[input] << bit, 0);
      values[net] = table[index];
    }
  };
  for (const [q, , reset] of model.ffs) if (reset !== null) values[q] = reset;
  settle({A: 0, B: 0, en: 0, rst_n: 0, clk: 0});
  const frames = [];
  for (let bit = 7; bit >= 0; bit--) {
    const inputs = {A: a >> bit & 1, B: b >> bit & 1, en: 1, rst_n: 1, clk: 0};
    settle(inputs);
    frames.push(values.slice());
    const captured = model.ffs.map(([, d]) => values[d]);
    model.ffs.forEach(([q], index) => { values[q] = captured[index]; });
    for (const [q, , reset, resetNet] of model.ffs) {
      if (resetNet !== null && values[resetNet] === 0) values[q] = reset;
    }
    settle(inputs);
    settle({...inputs, clk: 1});
    frames.push(values.slice());
  }
  return frames;
}

async function loadScene() {
  const response = await fetch(document.body.dataset.scene);
  if (!response.ok) throw new Error(`Scene request failed: ${response.status}`);
  const data = await new Response(response.body.pipeThrough(new DecompressionStream("gzip"))).json();
  const stage = document.getElementById("scene-stage");
  const scene = new THREE.Scene();
  THREE.Object3D.DEFAULT_UP.set(0, 0, 1);
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  stage.append(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(data.fov, 1, .01, 10000);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enablePan = false;
  renderer.domElement.addEventListener("pointerdown", event => {
    controls.enablePan = event.button === 0 && event.ctrlKey;
  }, true);
  scene.add(new THREE.AmbientLight(0xffffff, 1.4));
  const light = new THREE.DirectionalLight(0xffffff, 2);
  light.position.set(1, -2, 3);
  scene.add(light);

  const hidden = new Set(data.hidden);
  const selectedNet = {value: -1};
  const pinnedPolygon = {value: false};
  const selectionBrightness = {value: 0};
  let pinned = null;
  let hoverPointer = null;
  const colorNets = {value: false};
  let highlightNets = false;
  let centerNets = false;
  const meshes = data.objects.map(object => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(object.vertices, 3));
    geometry.setIndex(object.indices);
    const material = new THREE.MeshStandardMaterial({
      color: object.color, flatShading: true, roughness: .8, side: THREE.DoubleSide,
      transparent: object.opacity < 1, depthWrite: object.opacity >= 1, opacity: object.opacity,
    });
    if (object.net_ids.length) {
      geometry.setAttribute("netId", new THREE.Float32BufferAttribute(object.net_ids, 1));
      const colors = new Float32Array(object.net_ids.length * 3);
      const color = new THREE.Color();
      object.net_ids.forEach((net, index) => {
        color.setHex(data.net_colors[net] ?? object.color).toArray(colors, index * 3);
      });
      geometry.setAttribute("netColor", new THREE.BufferAttribute(colors, 3));
    }
    material.defaultAttributeValues = {selectionMask: [0]};
    material.onBeforeCompile = shader => {
      shader.uniforms.pinnedPolygon = pinnedPolygon;
      shader.uniforms.selectionBrightness = selectionBrightness;
      shader.vertexShader = "attribute float selectionMask; varying float vSelectionMask;\n" + shader.vertexShader;
      shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>",
        "#include <begin_vertex>\nvSelectionMask = selectionMask;");
      shader.fragmentShader = "uniform bool pinnedPolygon; uniform float selectionBrightness; varying float vSelectionMask;\n" + shader.fragmentShader;
      shader.fragmentShader = shader.fragmentShader.replace("#include <color_fragment>",
        `#include <color_fragment>
        if (pinnedPolygon) {
          diffuseColor.a *= mix(0.04, 1.0, vSelectionMask);
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0), selectionBrightness * vSelectionMask);
        }`);
      if (object.net_ids.length) {
        shader.uniforms.selectedNet = selectedNet;
        shader.uniforms.colorNets = colorNets;
        shader.vertexShader = "attribute float netId; attribute vec3 netColor; varying float vNetId; varying vec3 vNetColor;\n" + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>",
          "#include <begin_vertex>\nvNetId = netId; vNetColor = netColor;");
        shader.fragmentShader = "uniform float selectedNet; uniform bool colorNets; varying float vNetId; varying vec3 vNetColor;\n" + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace("#include <color_fragment>",
          `#include <color_fragment>
          if (colorNets) diffuseColor.rgb = vNetColor;
          if (selectedNet >= 0.0) {
            if (abs(vNetId - selectedNet) >= 0.5) diffuseColor.a *= 0.04;
            else diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0), selectionBrightness);
          }`);
      }
    };
    material.customProgramCacheKey = () => object.net_ids.length ? "net-selection" : "polygon-selection";
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.netIds = object.net_ids;
    mesh.name = object.name;
    mesh.visible = !hidden.has(object.id);
    mesh.applyMatrix4(new THREE.Matrix4().fromArray(object.model_matrix).transpose());
    scene.add(mesh);
    return mesh;
  });

  const dark = () => document.documentElement.dataset.theme === "dark";
  const gizmoOptions = () => {
    const face = {color: dark() ? "#8da5c5" : "#e9eff8", labelColor: dark() ? "#ffffff" : "#192b46"};
    return {
      container: stage, type: "cube", size: 78, placement: "top-right",
      offset: {top: 57, right: 14}, className: "orientation-cube", background: {enabled: false},
      corners: {color: dark() ? "#526780" : "#cdd9e9"},
      edges: {color: dark() ? "#526780" : "#cdd9e9"},
      x: {...face, label: "RIGHT"}, nx: {...face, label: "LEFT"},
      y: {...face, label: "BACK"}, ny: {...face, label: "FRONT"},
      z: {...face, label: "TOP"}, nz: {...face, label: "BOTTOM"},
    };
  };
  const gizmo = new ViewportGizmo(camera, renderer, gizmoOptions());
  gizmo.attachControls(controls);
  let pending = false;
  const render = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      renderer.render(scene, camera);
      gizmo.render();
      if (gizmo.animating) render();
    });
  };
  controls.addEventListener("change", render);
  gizmo.addEventListener("start", render);
  gizmo.addEventListener("change", () => {
    camera.up.set(0, 0, 1);
    controls.update();
    render();
  });
  const updateBackground = () => {
    renderer.setClearColor(dark() ? 0x101d30 : 0xf6f9fd);
    render();
  };
  renderer.domElement.addEventListener("webglcontextrestored", updateBackground);
  const updateTheme = () => {
    selectionBrightness.value = dark() ? .2 : 0;
    gizmo.set(gizmoOptions());
    gizmo.attachControls(controls);
    updateBackground();
  };
  window.addEventListener("asic-theme-change", updateTheme);
  updateTheme();
  const reset = () => {
    clearSelection();
    clearHighlight();
    const bounds = new THREE.Box3();
    meshes.filter(mesh => mesh.visible).forEach(mesh => bounds.expandByObject(mesh));
    if (bounds.isEmpty()) return;
    const offset = new THREE.Vector3().fromArray(data.camera)
      .sub(new THREE.Vector3().fromArray(data.camera.slice(3, 6))).normalize();
    bounds.getCenter(controls.target);
    // Fit the projected bounds, including depth, inside the space between controls.
    const right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 0, 1), offset);
    if (right.lengthSq() < 1e-10) right.set(1, 0, 0);
    right.normalize();
    const up = new THREE.Vector3().crossVectors(offset, right);
    const tanY = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * .78;
    const tanX = tanY * stage.clientWidth / stage.clientHeight;
    let distance = 0;
    for (const x of [bounds.min.x, bounds.max.x]) {
      for (const y of [bounds.min.y, bounds.max.y]) {
        for (const z of [bounds.min.z, bounds.max.z]) {
          const point = new THREE.Vector3(x, y, z).sub(controls.target);
          distance = Math.max(distance, point.dot(offset) +
            Math.max(Math.abs(point.dot(right)) / tanX, Math.abs(point.dot(up)) / tanY));
        }
      }
    }
    camera.position.copy(controls.target).addScaledVector(offset, distance);
    camera.up.set(0, 0, 1);
    controls.update();
    gizmo.update();
    render();
  };
  const resize = new ResizeObserver(() => {
    const width = stage.clientWidth, height = stage.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    gizmo.update();
    render();
  });
  resize.observe(stage);

  const toolbar = document.createElement("div");
  toolbar.className = "view-toolbar";
  const button = (parent, label, action) => {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.addEventListener("click", action);
    parent.append(element);
    return element;
  };
  button(toolbar, "Reset view", reset);
  const navigation = document.createElement("div");
  navigation.className = "view-navigation";
  const zoom = document.createElement("div");
  zoom.className = "zoom-controls";
  for (const [label, title, factor] of [["+", "Zoom in", .8], ["−", "Zoom out", 1.25]]) {
    button(zoom, label, () => {
      camera.position.sub(controls.target).multiplyScalar(factor).add(controls.target);
      controls.update();
      render();
    }).setAttribute("aria-label", title);
  }
  navigation.append(zoom);
  document.body.append(navigation);

  const info = document.createElement("div");
  info.className = "mesh-info";
  info.textContent = "Hover to inspect · Click to center";
  document.body.append(info);
  if (data.presets.length) {
    const applyPreset = preset => {
      const ids = new Set(preset.ids);
      highlightNets = preset.highlight_nets === true;
      centerNets = highlightNets || preset.center_nets === true;
      colorNets.value = highlightNets;
      clearSelection();
      clearHighlight();
      meshes.forEach((mesh, index) => {
        mesh.visible = ids.has(data.objects[index].id);
      });
      render();
    };
    if (data.presets.some(preset => preset.color !== undefined)) {
      const choices = document.createElement("div");
      choices.className = "layer-choices";
      choices.setAttribute("role", "group");
      choices.setAttribute("aria-label", "Visible geometry");
      data.presets.forEach((preset, index) => {
        const choice = button(choices, preset.label, () => {
          applyPreset(preset);
          [...choices.children].forEach(item => item.setAttribute("aria-pressed", item === choice));
        });
        choice.setAttribute("aria-pressed", index === 0);
        if (preset.color !== undefined) {
          choice.style.setProperty("--layer-color", `#${preset.color.toString(16).padStart(6, "0")}`);
        }
      });
      document.body.append(choices);
    } else {
      const select = document.createElement("select");
      select.setAttribute("aria-label", "Visible geometry");
      data.presets.forEach((preset, index) => select.add(new Option(preset.label, index)));
      select.addEventListener("change", () => applyPreset(data.presets[select.value]));
      toolbar.append(select);
    }
    applyPreset(data.presets[0]);
  }
  const hint = document.createElement("span");
  hint.className = "view-hint";
  hint.textContent = "Drag to rotate · Ctrl-drag to pan · Scroll to zoom";
  toolbar.append(hint);
  document.body.append(toolbar);

  function selectNet(net) {
    selectedNet.value = net;
    const active = net >= 0 || pinnedPolygon.value;
    meshes.forEach((mesh, index) => {
      const opacity = data.objects[index].opacity;
      const transparent = active || opacity < 1;
      const depthWrite = !active && opacity >= 1;
      const selected = net >= 0 && mesh.userData.netIds.length || pinnedPolygon.value && pinned?.mesh === mesh;
      mesh.material.opacity = selected ? 1 : opacity * (net >= 0 ? .04 : 1);
      if (mesh.material.transparent !== transparent || mesh.material.depthWrite !== depthWrite) {
        mesh.material.transparent = transparent;
        mesh.material.depthWrite = depthWrite;
        mesh.material.needsUpdate = true;
      }
    });
  }
  function clearSelection() {
    const mask = pinned?.mesh.geometry.getAttribute("selectionMask");
    if (mask) {
      mask.array.fill(0);
      mask.needsUpdate = true;
    }
    pinned = null;
    pinnedPolygon.value = false;
  }
  function clearHighlight() {
    hoverPointer = null;
    selectNet(pinned?.net ?? -1);
    info.textContent = pinned
      ? `Selected ${pinned.net >= 0 ? `n${pinned.net} · ` : ""}${pinned.mesh.name} · Reset to clear`
      : highlightNets ? "Hover to isolate a net · Click to select" : "Hover to inspect · Click to select";
    render();
  }
  renderer.domElement.addEventListener("pointerleave", clearHighlight);
  controls.addEventListener("start", clearHighlight);
  const raycaster = new THREE.Raycaster();
  const pick = (clientX, clientY) => {
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2((clientX - rect.left) / rect.width * 2 - 1,
      1 - (clientY - rect.top) / rect.height * 2), camera);
    return raycaster.intersectObjects(meshes.filter(mesh => mesh.visible))[0];
  };
  let press;
  renderer.domElement.addEventListener("pointerdown", event => {
    press = event.button === 0 && !event.ctrlKey ? [event.clientX, event.clientY] : null;
  });
  renderer.domElement.addEventListener("pointerup", event => {
    const start = press;
    press = null;
    if (!start || Math.hypot(event.clientX - start[0], event.clientY - start[1]) > 4) return;
    const hit = pick(event.clientX, event.clientY);
    if (!hit) return;
    const vertex = hit.object.geometry.index.array[hit.faceIndex * 3];
    const net = centerNets ? hit.object.userData.netIds[vertex] ?? -1 : -1;
    clearSelection();
    const bounds = new THREE.Box3();
    const point = new THREE.Vector3();
    for (const mesh of net >= 0 ? meshes.filter(mesh => mesh.visible) : [hit.object]) {
      const geometry = mesh.geometry;
      let roots;
      if (!(net >= 0)) {
        roots = geometry.userData.components;
        if (!roots) {
          roots = Uint32Array.from({length: geometry.attributes.position.count}, (_, i) => i);
          const root = index => {
            while (roots[index] !== index) { roots[index] = roots[roots[index]]; index = roots[index]; }
            return index;
          };
          const indices = geometry.index.array;
          for (let i = 0; i < indices.length; i += 3) {
            roots[root(indices[i + 1])] = root(indices[i]);
            roots[root(indices[i + 2])] = root(indices[i]);
          }
          roots.forEach((_, index) => { roots[index] = root(index); });
          geometry.userData.components = roots;
        }
      }
      const local = new THREE.Box3();
      let mask = geometry.getAttribute("selectionMask");
      if (net < 0 && !mask) {
        mask = new THREE.BufferAttribute(new Float32Array(geometry.attributes.position.count), 1);
        geometry.setAttribute("selectionMask", mask);
      }
      for (let i = 0; i < geometry.attributes.position.count; i++) {
        if (net >= 0 ? mesh.userData.netIds[i] === net : roots[i] === roots[vertex]) {
          local.expandByPoint(point.fromBufferAttribute(geometry.attributes.position, i));
          if (net < 0) mask.array[i] = 1;
        }
      }
      if (net < 0) mask.needsUpdate = true;
      bounds.union(local.applyMatrix4(mesh.matrixWorld));
    }
    if (bounds.isEmpty()) return;
    pinned = {net, mesh: hit.object};
    pinnedPolygon.value = net < 0;
    const target = bounds.getCenter(point);
    camera.position.add(new THREE.Vector3().subVectors(target, controls.target));
    controls.target.copy(target);
    controls.update();
    clearHighlight();
  });
  renderer.domElement.addEventListener("pointercancel", () => { press = null; });
  let pointerPending = false;
  renderer.domElement.addEventListener("pointermove", event => {
    if (press && Math.hypot(event.clientX - press[0], event.clientY - press[1]) > 4) press = null;
    if (event.buttons || pinned) { hoverPointer = null; return; }
    hoverPointer = [event.clientX, event.clientY];
    if (pointerPending) return;
    pointerPending = true;
    requestAnimationFrame(() => {
      pointerPending = false;
      if (!hoverPointer || pinned) return;
      const hit = pick(...hoverPointer);
      const net = highlightNets && hit
        ? hit.object.userData.netIds[hit.object.geometry.index.array[hit.faceIndex * 3]] : -1;
      selectNet(net >= 0 ? net : -1);
      info.textContent = hit ? (net >= 0 ? `n${net} · ` : "") + hit.object.name
        : highlightNets ? "Hover to isolate a net · Click to select" : "Hover to inspect · Click to select";
      render();
    });
  });

  const times = [...new Set(data.objects.flatMap(object =>
    Array.isArray(object.attribute) ? [] : Object.keys(object.attribute).map(Number)))].sort((a, b) => a - b);
  const color = new THREE.Color();
  const setTime = (time, state) => {
    data.objects.forEach((object, index) => {
      let attribute = object.attribute;
      if (!Array.isArray(attribute)) {
        const keys = Object.keys(attribute).sort((a, b) => Number(a) - Number(b));
        attribute = attribute[keys.filter(key => Number(key) <= time).at(-1) ?? keys[0]];
      }
      if (state && object.id === data.simulation.signal_mesh) attribute = object.net_ids.map(net => state[net]);
      if (!object.colors.length && !attribute?.length) return;
      const count = object.vertices.length / 3;
      const mesh = meshes[index];
      let colors = mesh.geometry.getAttribute("color");
      if (!colors) {
        colors = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
        mesh.geometry.setAttribute("color", colors);
        mesh.material.color.setHex(0xffffff);
        mesh.material.vertexColors = true;
        mesh.material.needsUpdate = true;
      }
      for (let vertex = 0; vertex < count; vertex++) {
        if (object.colors.length) color.setHex(object.colors[vertex]);
        else {
          const map = object.color_map;
          const [low, high] = object.color_range;
          const scalar = Math.max(0, Math.min(1, (attribute[vertex] - low) / (high - low || 1)));
          let stop = 0;
          while (stop + 4 < map.length && scalar > map[stop + 4]) stop += 4;
          const next = Math.min(stop + 4, map.length - 4);
          const fraction = next === stop ? 0 : (scalar - map[stop]) / (map[next] - map[stop]);
          color.setRGB(...[1, 2, 3].map(channel => map[stop + channel] * (1 - fraction)
            + map[next + channel] * fraction), THREE.SRGBColorSpace);
        }
        color.toArray(colors.array, vertex * 3);
      }
      colors.needsUpdate = true;
    });
    render();
  };
  setTime(times[0] ?? 0);
  if (times.length) {
    const key = document.createElement("div");
    key.className = "signal-key";
    key.innerHTML = '<span class="signal-low">●</span> 0 <span class="signal-high">●</span> 1';
    document.body.append(key);
    const playback = document.createElement("div");
    playback.className = "scene-playback";
    const playbackControls = document.createElement("div");
    const readoutRow = document.createElement("div");
    readoutRow.className = "replay-readout";
    const readout = document.createElement("pre");
    let inputs = data.simulation?.inputs;
    let states = inputs ? simulateWarmup(data.simulation, ...inputs) : null;
    const resetPlayback = window.createPlayback(playbackControls, states?.length ?? times.length, frame => {
      setTime(times[frame], states?.[frame]);
      if (states) {
        const edge = Math.floor(frame / 2);
        const bits = inputs.map((value, i) => {
          const binary = value.toString(2).padStart(8, "0");
          return `${i ? "B" : "A"}=0b${binary.slice(0, edge)}[${binary[edge]}]${binary.slice(edge + 1)}`;
        }).join("  ");
        const signals = ["en", "clk", "rst_n", "S"].map(pin => `${pin}=${states[frame][data.simulation.ports[pin]]}`).join("  ");
        window.showInputBits(readout, `Edge ${edge + 1} · ${frame % 2 ? "post" : "pre"}-edge\n${bits}\n${signals}`);
      } else readout.textContent = data.readouts[frame] ?? `t = ${times[frame]}`;
    });
    readoutRow.append(readout);
    playback.append(playbackControls, readoutRow);
    if (data.simulation) {
      const inputRow = document.createElement("div");
      inputRow.className = "replay-inputs";
      const fields = [];
      for (const [index, name] of ["A", "B"].entries()) {
        const label = document.createElement("label");
        label.append(`${name} `);
        const field = document.createElement("input");
        field.type = "text";
        field.inputMode = "numeric";
        field.required = true;
        field.value = inputs[index];
        label.append(field);
        inputRow.append(label);
        fields.push(field);
      }
      const range = document.createElement("span");
      range.textContent = "0–255";
      inputRow.append(range);
      const updateInputs = normalize => {
        const values = fields.map(field => Number(field.value));
        fields.forEach((field, index) => field.setCustomValidity(
          field.value.trim() && Number.isFinite(values[index]) ? "" : "Enter a number."));
        if (fields.some(field => !field.validity.valid)) return;
        const next = values.map(value => Math.max(0, Math.min(255, Math.trunc(value))));
        if (normalize) fields.forEach((field, index) => { field.value = next[index]; });
        if (next.every((value, index) => value === inputs[index])) return;
        inputs = next;
        states = simulateWarmup(data.simulation, ...inputs);
        resetPlayback(states.length);
      };
      fields.forEach(field => {
        field.addEventListener("input", () => updateInputs(false));
        field.addEventListener("change", () => updateInputs(true));
      });
      playback.append(inputRow);
    }
    document.body.append(playback);
    info.classList.add("with-playback");
  }
  reset();
  document.getElementById("scene-status").remove();
  window.addEventListener("pagehide", event => {
    if (event.persisted) return;
    resize.disconnect();
    gizmo.dispose();
    controls.dispose();
    meshes.forEach(mesh => { mesh.geometry.dispose(); mesh.material.dispose(); });
    renderer.dispose();
  });
}

loadScene().catch(error => {
  document.getElementById("scene-status").textContent = "This 3D figure could not load. Please reload the page in a browser with WebGL2 enabled.";
  console.error(error);
});
