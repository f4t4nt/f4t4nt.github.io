/* Shared hover-highlight behavior for any svg.gdiagram on the page. */
(function () {
  "use strict";

  function splitAttr(el, name) {
    var v = el.getAttribute(name);
    return v ? v.split(",") : null;
  }

  function initGraphDiagram(svg) {
    var edges = Array.prototype.slice.call(svg.querySelectorAll(".gedge"));
    var visibleNodes = Array.prototype.slice.call(svg.querySelectorAll(".gnode"));
    var hitNodes = Array.prototype.slice.call(svg.querySelectorAll(".ghit"));
    if (!hitNodes.length) return;

    var pos = Object.create(null);
    hitNodes.forEach(function (el) {
      pos[el.getAttribute("data-v")] = { cx: el.getAttribute("cx"), cy: el.getAttribute("cy") };
    });

    // parse each .gedge's data-* once; every pass below reads from here
    var elemInfo = edges.map(function (el) {
      return {
        el: el,
        hub: el.getAttribute("data-hub"),
        far: splitAttr(el, "data-far"),
        ids: splitAttr(el, "data-ids"),
        u: el.getAttribute("data-u"),
        w: el.getAttribute("data-w"),
      };
    });

    // sets, not arrays -- several .gedge elements can back one logical edge
    var adjSets = Object.create(null);
    function link(a, b) {
      (adjSets[a] || (adjSets[a] = Object.create(null)))[b] = true;
    }
    elemInfo.forEach(function (info) {
      if (info.hub) {
        info.far.forEach(function (port) {
          link(info.hub, port);
          link(port, info.hub);
        });
      }
      // data-ids is a hover-trigger list, not an edge pairing -- skip it here
      if (info.hub || info.ids) return;
      if (!info.u || !info.w) return;
      link(info.u, info.w);
      link(info.w, info.u);
    });
    var adj = Object.create(null);
    var maxDeg = 0;
    Object.keys(adjSets).forEach(function (label) {
      adj[label] = Object.keys(adjSets[label]);
      maxDeg = Math.max(maxDeg, adj[label].length);
    });

    var MARKER_SIZE = 9.5;
    var NEIGHBOR_SIZE = 9;
    function placeSquare(el, cx, cy, size) {
      el.setAttribute("x", parseFloat(cx) - size / 2);
      el.setAttribute("y", parseFloat(cy) - size / 2);
    }

    var marker = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    marker.setAttribute("class", "hover-marker");
    marker.setAttribute("width", MARKER_SIZE);
    marker.setAttribute("height", MARKER_SIZE);
    marker.setAttribute("rx", "2.2");
    svg.appendChild(marker);

    // sized to this diagram's own max degree, not the full graph's
    var neighborMarkers = [];
    for (var i = 0; i < maxDeg; i++) {
      var nm = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      nm.setAttribute("class", "hover-marker hover-marker-neighbor");
      nm.setAttribute("width", NEIGHBOR_SIZE);
      nm.setAttribute("height", NEIGHBOR_SIZE);
      nm.setAttribute("rx", "1.8");
      svg.appendChild(nm);
      neighborMarkers.push(nm);
    }

    function placeNeighborMarkers(labels) {
      neighborMarkers.forEach(function (nm, idx) {
        var v = labels[idx];
        var p = v && pos[v];
        if (p) {
          placeSquare(nm, p.cx, p.cy, NEIGHBOR_SIZE);
          nm.removeAttribute("data-hidden");
        } else {
          nm.setAttribute("data-hidden", "1");
        }
      });
    }

    function setNear(labelSet) {
      visibleNodes.forEach(function (el) {
        if (labelSet[el.getAttribute("data-v")]) el.setAttribute("data-near", "1");
        else el.removeAttribute("data-near");
      });
    }

    function highlight(label, cx, cy) {
      var near = Object.create(null);
      near[label] = true;
      var neighbors = adj[label] || [];
      neighbors.forEach(function (v) { near[v] = true; });

      svg.setAttribute("data-hover", "1");
      marker.removeAttribute("data-hidden");
      placeSquare(marker, cx, cy, MARKER_SIZE);
      placeNeighborMarkers(neighbors);
      setNear(near);

      elemInfo.forEach(function (info) {
        var el = info.el;
        var onPath;

        if (info.hub || info.ids) {
          onPath = false;
          if (info.hub && (label === info.hub || info.far.indexOf(label) !== -1)) onPath = true;
          if (info.ids && info.ids.indexOf(label) !== -1) onPath = true;
        } else {
          // u/w are linked into adj by this same element, so label===u already implies w is near
          onPath = info.u === label || info.w === label;
        }

        if (onPath) el.setAttribute("data-onpath", "1");
        else el.removeAttribute("data-onpath");
        el.removeAttribute("data-edgehover");
      });
    }

    function edgeConnects(info, a, b) {
      if (info.hub && ((info.hub === a && info.far.indexOf(b) !== -1) || (info.hub === b && info.far.indexOf(a) !== -1))) return true;
      if (info.ids && info.ids.indexOf(a) !== -1 && info.ids.indexOf(b) !== -1) return true;
      if (!info.hub && !info.ids) {
        if ((info.u === a && info.w === b) || (info.u === b && info.w === a)) return true;
      }
      return false;
    }

    function highlightEdge(a, b) {
      svg.setAttribute("data-hover", "1");
      marker.setAttribute("data-hidden", "1");
      var near = Object.create(null);
      near[a] = true;
      near[b] = true;
      setNear(near);
      placeNeighborMarkers([a, b]);

      elemInfo.forEach(function (info) {
        var el = info.el;
        el.removeAttribute("data-onpath");
        if (edgeConnects(info, a, b)) el.setAttribute("data-edgehover", "1");
        else el.removeAttribute("data-edgehover");
      });
    }

    function clear() {
      svg.removeAttribute("data-hover");
      visibleNodes.forEach(function (el) {
        el.removeAttribute("data-near");
      });
      edges.forEach(function (el) {
        el.removeAttribute("data-onpath");
        el.removeAttribute("data-edgehover");
      });
    }

    hitNodes.forEach(function (hit) {
      hit.addEventListener("pointerenter", function () {
        highlight(hit.getAttribute("data-v"), hit.getAttribute("cx"), hit.getAttribute("cy"));
      });
      hit.addEventListener("pointerleave", clear);
    });

    // hit-test the drawn geometry itself, not proximity to a node -- bridges run long
    var EDGE_HOVER_TOLERANCE_SQ = 4.5 * 4.5;

    function parsePoints(el) {
      if (el.hasAttribute("x1")) {
        return [
          [parseFloat(el.getAttribute("x1")), parseFloat(el.getAttribute("y1"))],
          [parseFloat(el.getAttribute("x2")), parseFloat(el.getAttribute("y2"))],
        ];
      }
      var nums = (el.getAttribute("d") || "").match(/-?\d+\.?\d*/g) || [];
      var pts = [];
      for (var i = 0; i + 1 < nums.length; i += 2) {
        pts.push([parseFloat(nums[i]), parseFloat(nums[i + 1])]);
      }
      return pts;
    }

    function distToSegSq(px, py, x1, y1, x2, y2) {
      var dx = x2 - x1, dy = y2 - y1;
      var lenSq = dx * dx + dy * dy;
      var t = lenSq > 0 ? ((px - x1) * dx + (py - y1) * dy) / lenSq : 0;
      t = Math.max(0, Math.min(1, t));
      var ex = px - (x1 + t * dx), ey = py - (y1 + t * dy);
      return ex * ex + ey * ey;
    }

    // a data-ids trunk names no pair directly -- recover its pairs from adj
    var hitSegments = [];
    elemInfo.forEach(function (info) {
      var labelSet = Object.create(null);
      var pairs = [];
      function addPair(a, b) {
        labelSet[a] = true;
        labelSet[b] = true;
        pairs.push([a, b]);
      }
      if (info.hub) info.far.forEach(function (far) { addPair(info.hub, far); });
      if (info.u && info.w) addPair(info.u, info.w);
      if (info.ids) {
        var idsSet = Object.create(null);
        info.ids.forEach(function (v) { idsSet[v] = true; });
        Object.keys(idsSet).forEach(function (v) {
          (adj[v] || []).forEach(function (n) {
            if (idsSet[n]) addPair(v, n);
          });
        });
      }
      if (!pairs.length) return;
      var labels = Object.keys(labelSet);
      var pts = parsePoints(info.el);
      for (var i = 0; i + 1 < pts.length; i++) {
        hitSegments.push({
          x1: pts[i][0], y1: pts[i][1], x2: pts[i + 1][0], y2: pts[i + 1][1],
          labels: labels, pairs: pairs,
        });
      }
    });

    // geometry -> logical pair; split out so tests can call it directly
    var TIE_EPS = 1e-6;
    function cornerDistSq(seg, x, y) {
      var d1x = seg.x1 - x, d1y = seg.y1 - y;
      var d2x = seg.x2 - x, d2y = seg.y2 - y;
      return Math.min(d1x * d1x + d1y * d1y, d2x * d2x + d2y * d2y);
    }
    function resolveEdgeAt(x, y) {
      var best = null, bestD = Infinity, bestCornerD = Infinity;
      hitSegments.forEach(function (seg) {
        var d = distToSegSq(x, y, seg.x1, seg.y1, seg.x2, seg.y2);
        if (d > bestD + TIE_EPS) return;
        // coincident corridor trunks tie on distance -- break by nearest dock, not draw order
        var cd = cornerDistSq(seg, x, y);
        if (d < bestD - TIE_EPS || cd < bestCornerD) {
          best = seg; bestD = d; bestCornerD = cd;
        }
      });
      if (!best || bestD > EDGE_HOVER_TOLERANCE_SQ) return null;

      // nearer end of this piece...
      var a = null, bestNodeD = Infinity;
      best.labels.forEach(function (label) {
        var p = pos[label];
        if (!p) return;
        var dx = parseFloat(p.cx) - x, dy = parseFloat(p.cy) - y;
        var d = dx * dx + dy * dy;
        if (d < bestNodeD) { bestNodeD = d; a = label; }
      });
      if (!a) return null;

      // ...then the closer far end wins
      var b = null, bestScore = Infinity;
      best.pairs.forEach(function (pair) {
        var v = pair[0] === a ? pair[1] : pair[1] === a ? pair[0] : null;
        if (!v) return;
        var p = pos[v];
        if (!p) return;
        var dx = parseFloat(p.cx) - x, dy = parseFloat(p.cy) - y;
        var d = Math.sqrt(dx * dx + dy * dy);
        if (d < bestScore) { bestScore = d; b = v; }
      });
      if (!b) return null;
      return { a: a, b: b };
    }

    svg.addEventListener("pointermove", function (evt) {
      if (evt.target.classList && evt.target.classList.contains("ghit")) return;
      var ctm = svg.getScreenCTM();
      if (!ctm) return;
      var pt = svg.createSVGPoint();
      pt.x = evt.clientX;
      pt.y = evt.clientY;
      var loc = pt.matrixTransform(ctm.inverse());

      var pair = resolveEdgeAt(loc.x, loc.y);
      if (!pair) {
        clear();
        return;
      }
      highlightEdge(pair.a, pair.b);
    });
    svg.addEventListener("pointerleave", clear);

    // exposed for tools/test_hover.py
    var handle = {
      svg: svg,
      adj: adj,
      pos: pos,
      hitSegments: hitSegments,
      highlight: highlight,
      highlightEdge: highlightEdge,
      clear: clear,
      resolveEdgeAt: resolveEdgeAt,
    };
    svg.__ghDiagram = handle;
    return handle;
  }

  window.initGraphDiagram = initGraphDiagram;
})();
