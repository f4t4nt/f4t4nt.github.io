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
    var groupLabels = Array.prototype.slice.call(svg.querySelectorAll(".glabel"));
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
    Object.keys(adjSets).forEach(function (label) {
      adj[label] = Object.keys(adjSets[label]);
    });

    // The vertex pairs one .gedge element stands for. A spoke element names its
    // pair outright; a data-ids trunk names none, so its pairs are whichever of
    // the vertices it lists are actually adjacent.
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
      info.pairs = pairs;
      info.labels = Object.keys(labelSet);
    });

    var NONE = Object.create(null);

    // data-near is the lit set (what is hovered, plus its neighbors); data-active
    // is what is hovered exactly, so CSS can give it its own look
    function setFlag(name, labelSet) {
      visibleNodes.forEach(function (el) {
        if (labelSet[el.getAttribute("data-v")]) el.setAttribute(name, "1");
        else el.removeAttribute(name);
      });
    }

    function highlight(label) {
      var near = Object.create(null);
      near[label] = true;
      var neighbors = adj[label] || [];
      neighbors.forEach(function (v) { near[v] = true; });

      var active = Object.create(null);
      active[label] = true;

      svg.setAttribute("data-hover", "1");
      setFlag("data-near", near);
      setFlag("data-active", active);
      setFlag("data-pin", NONE);

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

    // Hovering a silkscreen name hovers the whole set of vertices it stands for,
    // which makes the edges divide in a way a single vertex never does: both ends
    // inside the set is the set's own structure, one end outside is how it is
    // attached to the rest. What each name stands for is the page's business --
    // this only reads the list.
    function highlightGroup(members) {
      var inside = Object.create(null);
      var near = Object.create(null);
      members.forEach(function (v) {
        inside[v] = true;
        near[v] = true;
        (adj[v] || []).forEach(function (n) { near[n] = true; });
      });

      svg.setAttribute("data-hover", "1");
      setFlag("data-near", near);
      setFlag("data-active", inside);
      setFlag("data-pin", NONE);

      elemInfo.forEach(function (info) {
        var ends = 0;
        info.pairs.forEach(function (pair) {
          var n = (inside[pair[0]] ? 1 : 0) + (inside[pair[1]] ? 1 : 0);
          if (n > ends) ends = n;
        });
        var el = info.el;
        if (ends === 2) el.setAttribute("data-ingroup", "1");
        else el.removeAttribute("data-ingroup");
        if (ends === 1) el.setAttribute("data-onpath", "1");
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
      var near = Object.create(null);
      near[a] = true;
      near[b] = true;
      setFlag("data-near", near);

      elemInfo.forEach(function (info) {
        var el = info.el;
        el.removeAttribute("data-onpath");
        if (edgeConnects(info, a, b)) el.setAttribute("data-edgehover", "1");
        else el.removeAttribute("data-edgehover");
      });
    }

    function clearEdges() {
      edges.forEach(function (el) {
        el.removeAttribute("data-onpath");
        el.removeAttribute("data-ingroup");
        el.removeAttribute("data-edgehover");
      });
    }

    function clear() {
      svg.removeAttribute("data-hover");
      svg.removeAttribute("data-pinned");
      visibleNodes.forEach(function (el) {
        el.removeAttribute("data-near");
        el.removeAttribute("data-active");
        el.removeAttribute("data-pin");
      });
      clearEdges();
      groupLabels.forEach(function (el) { el.removeAttribute("data-active"); });
    }

    // A pinned source turns the diagram into one question -- how far is this
    // from there -- so while one is held, only another vertex answers it:
    // edges and silkscreen names stop responding until the pin is dropped.
    var pinnable = svg.getAttribute("data-pick") === "1";
    var pinned = null;

    // Breadth-first, stopping the moment b is reached. Ties go to whichever
    // neighbor the record named first, so the same pair always traces the
    // same path.
    function shortestPath(a, b) {
      if (a === b) return [a];
      var prev = Object.create(null);
      var seen = Object.create(null);
      var queue = [a];
      seen[a] = true;
      for (var i = 0; i < queue.length; i++) {
        var ns = adj[queue[i]] || [];
        for (var k = 0; k < ns.length; k++) {
          var n = ns[k];
          if (seen[n]) continue;
          seen[n] = true;
          prev[n] = queue[i];
          if (n === b) {
            var path = [b];
            while (path[0] !== a) path.unshift(prev[path[0]]);
            return path;
          }
          queue.push(n);
        }
      }
      return null;
    }

    function highlightPath(a, b) {
      var path = shortestPath(a, b);
      if (!path) path = [a];

      var near = Object.create(null);
      path.forEach(function (v) { near[v] = true; });
      var ends = Object.create(null);
      ends[a] = true;
      ends[path[path.length - 1]] = true;
      var source = Object.create(null);
      source[a] = true;

      svg.setAttribute("data-hover", "1");
      svg.setAttribute("data-pinned", "1");
      setFlag("data-near", near);
      setFlag("data-active", ends);
      setFlag("data-pin", source);
      groupLabels.forEach(function (el) { el.removeAttribute("data-active"); });

      elemInfo.forEach(function (info) {
        var on = false;
        for (var i = 0; i + 1 < path.length && !on; i++) {
          if (edgeConnects(info, path[i], path[i + 1])) on = true;
        }
        if (on) info.el.setAttribute("data-onpath", "1");
        else info.el.removeAttribute("data-onpath");
        info.el.removeAttribute("data-ingroup");
        info.el.removeAttribute("data-edgehover");
      });
    }

    // what the drawing shows with nothing under the pointer
    function rest() {
      if (pinned) highlightPath(pinned, pinned);
      else clear();
    }

    function unpin() {
      pinned = null;
      clear();
    }

    hitNodes.forEach(function (hit) {
      var label = hit.getAttribute("data-v");
      hit.addEventListener("pointerenter", function () {
        if (pinned) highlightPath(pinned, label);
        else highlight(label);
      });
      hit.addEventListener("pointerleave", rest);
      if (!pinnable) return;
      hit.addEventListener("click", function (evt) {
        evt.stopPropagation();
        if (pinned === label) {
          unpin();
          highlight(label);
        } else {
          pinned = label;
          highlightPath(label, label);
        }
      });
    });

    groupLabels.forEach(function (el) {
      var members = splitAttr(el, "data-group") || [];
      if (!members.length) return;
      el.addEventListener("pointerenter", function () {
        if (pinned) return;
        highlightGroup(members);
        el.setAttribute("data-active", "1");
      });
      el.addEventListener("pointerleave", rest);
    });

    if (pinnable) {
      // anywhere that is not a vertex drops the pin, as does Escape
      svg.addEventListener("click", unpin);
      document.addEventListener("keydown", function (evt) {
        if (evt.key === "Escape" && pinned) unpin();
      });
    }

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

    var hitSegments = [];
    elemInfo.forEach(function (info) {
      if (!info.pairs.length) return;
      var pts = parsePoints(info.el);
      for (var i = 0; i + 1 < pts.length; i++) {
        hitSegments.push({
          x1: pts[i][0], y1: pts[i][1], x2: pts[i + 1][0], y2: pts[i + 1][1],
          labels: info.labels, pairs: info.pairs,
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
      if (pinned) return;
      var cl = evt.target.classList;
      if (cl && (cl.contains("ghit") || cl.contains("glabel"))) return;
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
    svg.addEventListener("pointerleave", rest);

    // exposed for tools/test_hover.py
    var handle = {
      svg: svg,
      adj: adj,
      pos: pos,
      hitSegments: hitSegments,
      highlight: highlight,
      highlightGroup: highlightGroup,
      highlightEdge: highlightEdge,
      highlightPath: highlightPath,
      shortestPath: shortestPath,
      unpin: unpin,
      pinnedLabel: function () { return pinned; },
      clear: clear,
      resolveEdgeAt: resolveEdgeAt,
    };
    svg.__ghDiagram = handle;
    return handle;
  }

  window.initGraphDiagram = initGraphDiagram;
})();
