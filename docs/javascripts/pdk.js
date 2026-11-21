// Copyright (c) 2025-2026 Mark Buckwell and contributors
// SPDX-License-Identifier: MIT

document.addEventListener("DOMContentLoaded", function() {
  var links = document.querySelectorAll('a[href^="http"]');
  links.forEach(function(link) {
    if (!link.href.includes(window.location.host)) {
      link.target = "_blank";
      link.rel = "noopener";
    }
  });
});

// Grid cards remain the canonical source for static pages and PDF builds.
(function () {
  "use strict";
  const instances = new Map();
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let cloneId = 0;

  function enhance(root) {
    const list = Array.from(root.children).find(el => el.tagName === "UL");
    if (!list || list.children.length === 0) return null;
    const cards = Array.from(list.children);
    if (cards.some(el => el.tagName !== "LI" || el.hidden || el.hasAttribute("inert"))) return null;
    const saved = [root, list, ...cards].map(el => [el, Array.from(el.attributes, a => [a.name, a.value])]);
    const listeners = new AbortController();
    const on = (el, event, handler, options = {}) => el.addEventListener(event, handler, {...options, signal: listeners.signal});
    const controls = document.createElement("div");
    controls.className = "pdk-carousel-controls";
    const makeButton = (label, text, className, action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.className = className;
      button.setAttribute("aria-label", label);
      button.title = label;
      on(button, "click", action);
      controls.append(button);
      return button;
    };
    let start = 0;
    let visible = 1;
    let timer = null;
    let hovered = false;
    let focused = root.contains(document.activeElement);
    let printing = false;
    let paused = false;
    let stride = 0;
    let offset = 0;
    let finishMove = null;
    let animation = null;
    let pointer = null;
    let suppressClick = false;
    const loop = root.dataset.carouselLoop !== "false";
    const badges = [];
    const peek = root.dataset.carouselPeek === "true";
    const gap = /^\d+$/.test(root.dataset.carouselGap || "")
      ? Math.min(64, Number(root.dataset.carouselGap)) : 16;
    const autoplay = root.dataset.carouselAutoplay === "true";
    const interval = /^\d+$/.test(root.dataset.carouselInterval || "")
      ? Math.max(1000, Math.min(2147483647, Number(root.dataset.carouselInterval))) : 5000;
    const maxVisible = /^[1-9]\d*$/.test(root.dataset.carouselVisible || "")
      ? Number(root.dataset.carouselVisible) : 3;
    const minWidth = /^[1-9]\d*$/.test(root.dataset.carouselMinWidth || "")
      ? Math.max(80, Number(root.dataset.carouselMinWidth)) : 224;
    const durationValue = root.dataset.carouselDuration;
    const duration = /^\d+$/.test(durationValue || "") ? Math.min(2000, Number(durationValue)) : 600;
    const previous = makeButton("Previous cards", "‹", "pdk-carousel-arrow pdk-carousel-previous", () => move(-1, true));
    const next = makeButton("Next cards", "›", "pdk-carousel-arrow pdk-carousel-next", () => move(1, true));
    const toggle = autoplay && root.dataset.carouselPause !== "false" ? makeButton("Pause automatic rotation", "Pause automatic rotation", "pdk-carousel-toggle", () => {
      paused = !paused;
      schedule();
    }) : null;
    const position = document.createElement("span");
    position.className = "pdk-carousel-position";
    position.hidden = root.dataset.carouselPosition === "false";
    controls.append(position);
    const announcement = document.createElement("span");
    announcement.className = "pdk-carousel-announcement";
    announcement.setAttribute("aria-live", "polite");
    announcement.setAttribute("aria-atomic", "true");
    controls.append(announcement);
    const modulo = value => (value + cards.length) % cards.length;

    // Only edge buffers are copies. Remap IDs and local references (including
    // SVG defs), make copies inert, and exclude them from print and speech.
    function clone(card, order) {
      const copy = card.cloneNode(true);
      const elements = [copy, ...copy.querySelectorAll("*")];
      const ids = new Map();
      elements.forEach(el => { if (el.id) ids.set(el.id, `pdk-carousel-copy-${++cloneId}`); });
      elements.forEach(el => {
        if (el.id) el.id = ids.get(el.id);
        Array.from(el.attributes).forEach(attribute => {
          let value = attribute.value.replace(/url\(#([^)]*)\)/g, (all, id) => ids.has(id) ? `url(#${ids.get(id)})` : all);
          if (["href", "xlink:href"].includes(attribute.name) && value.startsWith("#") && ids.has(value.slice(1))) value = `#${ids.get(value.slice(1))}`;
          if (["for", "aria-labelledby", "aria-describedby", "aria-controls", "aria-owns"].includes(attribute.name)) value = value.split(/\s+/).map(id => ids.get(id) || id).join(" ");
          if (value !== attribute.value) el.setAttribute(attribute.name, value);
        });
      });
      copy.querySelectorAll("input, select, textarea, button").forEach(control => {
        control.disabled = true;
        control.removeAttribute("name");
        control.removeAttribute("form");
      });
      copy.removeAttribute("hidden");
      copy.setAttribute("data-pdk-carousel-clone", "");
      copy.setAttribute("aria-hidden", "true");
      copy.inert = true;
      copy.style.order = order;
      return copy;
    }
    const lastStart = () => Math.max(0, cards.length - visible);
    const atEnd = () => !loop && start >= lastStart();
    function schedule() {
      window.clearInterval(timer);
      timer = null;
      const running = autoplay && !paused && !hovered && !focused && !pointer &&
        !document.hidden && !motion.matches && !printing && cards.length > visible && !atEnd();
      if (running) timer = window.setInterval(() => move(1, false), Math.max(interval, duration + 100));
      if (toggle) {
        const label = atEnd() ? "Automatic rotation finished" : paused ? "Resume automatic rotation" : "Pause automatic rotation";
        toggle.textContent = label;
        toggle.setAttribute("aria-label", label);
        toggle.disabled = cards.length <= visible || motion.matches || atEnd();
        toggle.title = motion.matches ? "Automatic rotation is disabled by reduced motion" : label;
      }
    }
    function buffers() {
      list.querySelectorAll(":scope > [data-pdk-carousel-clone]").forEach(el => el.remove());
      if (!loop || cards.length <= visible) return;
      list.append(clone(cards[modulo(start - 2)], 0), clone(cards[modulo(start - 1)], 1),
        clone(cards[start], cards.length + 2), clone(cards[modulo(start + 1)], cards.length + 3));
    }
    function render() {
      const navigable = cards.length > visible;
      const looping = loop && navigable;
      const preview = peek && navigable;
      if (!printing) root.style.setProperty("--pdk-carousel-print-columns", visible);
      root.classList.toggle("pdk-carousel-peek", preview);
      root.style.setProperty("--pdk-carousel-visible", visible + (preview ? 1 : 0));
      cards.forEach((card, index) => {
        const order = loop ? modulo(index - start) : index - start;
        card.style.order = loop ? order + (looping ? 2 : 0) : index;
        card.inert = order < 0 || order >= visible;
        if (order >= 0 && order < visible) card.removeAttribute("aria-hidden");
        else card.setAttribute("aria-hidden", "true");
      });
      buffers();
      const width = cards[0].getBoundingClientRect().width;
      stride = width + gap;
      // Finite previews reserve half a card on each edge, leaving the
      // missing neighbour blank at an endpoint instead of cloning a card.
      offset = looping ? -(preview ? stride + width / 2 : 2 * stride)
        : (preview ? stride - width / 2 : 0) - start * stride;
      list.style.transform = `translateX(${offset}px)`;
      const numbers = Array.from({length: visible}, (_, i) => modulo(start + i) + 1);
      position.textContent = `Cards ${numbers.join(", ")} of ${cards.length}`;
      previous.disabled = !navigable || (!loop && start === 0);
      next.disabled = !navigable || atEnd();
      if ([previous, next].some(button => button.disabled && button === document.activeElement)) root.focus({preventScroll: true});
      root.classList.toggle("pdk-carousel-static", !navigable);
      delete root.dataset.carouselMoving;
      schedule();
    }
    function settle() {
      if (finishMove) { const finish = finishMove; finishMove = null; animation?.cancel(); animation = null; finish(); }
    }
    function move(direction, manual, drag = 0) {
      if (cards.length <= visible) return;
      settle();
      const target = loop ? modulo(start + direction) : Math.max(0, Math.min(lastStart(), start + direction));
      if (target === start) { list.style.transform = `translateX(${offset}px)`; schedule(); return; }
      if (cards.some(card => card.contains(document.activeElement))) root.focus({preventScroll: true});
      const finish = () => {
        start = target;
        render();
        if (manual) announcement.textContent = position.textContent;
      };
      if (motion.matches || printing || duration === 0 || !list.animate) { finish(); return; }
      root.dataset.carouselMoving = "true";
      finishMove = finish;
      animation = list.animate(
        [{transform: `translateX(${offset + drag}px)`}, {transform: `translateX(${offset - direction * stride}px)`}],
        {duration: Math.max(80, duration * (1 - Math.min(Math.abs(drag) / stride, 0.9))), easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards"}
      );
      animation.onfinish = settle;
    }
    function resize() {
      settle();
      const available = Math.max(1, Math.floor((root.clientWidth + gap) / (minWidth + gap)));
      visible = Math.min(cards.length, maxVisible, Math.max(1, available - (peek ? 1 : 0)));
      if (visible === cards.length) start = 0;
      const index = cards.findIndex(card => card.contains(document.activeElement));
      if (index >= 0 && (loop ? modulo(index - start) >= visible : index < start || index >= start + visible)) start = index;
      if (!loop) start = Math.max(0, Math.min(lastStart(), start));
      root.style.setProperty("--pdk-carousel-visible", visible + (peek && cards.length > visible ? 1 : 0));
      // Measure all original cards at the current width, not just the current
      // window. Every card keeps the same height throughout the entire loop.
      root.style.removeProperty("--pdk-carousel-height");
      const height = cards.reduce((maximum, card) => Math.max(maximum, card.getBoundingClientRect().height), 0);
      root.style.setProperty("--pdk-carousel-height", `${height}px`);
      render();
    }
    const observer = new ResizeObserver(resize);
    function destroy() {
      window.clearInterval(timer);
      finishMove = null;
      animation?.cancel();
      listeners.abort();
      observer.disconnect();
      controls.remove();
      badges.forEach(badge => badge.remove());
      list.querySelectorAll(":scope > [data-pdk-carousel-clone]").forEach(el => el.remove());
      saved.forEach(([el, attributes]) => {
        Array.from(el.attributes).forEach(a => el.removeAttribute(a.name));
        attributes.forEach(([name, value]) => el.setAttribute(name, value));
      });
    }
    try {
      root.setAttribute("role", "region");
      root.setAttribute("aria-roledescription", "carousel");
      if (!root.hasAttribute("aria-label") && !root.hasAttribute("aria-labelledby")) root.setAttribute("aria-label", root.dataset.carouselLabel || "Cards");
      root.setAttribute("tabindex", "-1");
      if (autoplay) {
        root.setAttribute("aria-keyshortcuts", "P");
        const hint = document.createElement("span");
        hint.id = `pdk-carousel-hint-${++cloneId}`;
        hint.className = "pdk-carousel-announcement";
        hint.textContent = "Press P while a carousel arrow has focus to pause or resume automatic rotation.";
        controls.append(hint);
        root.setAttribute("aria-describedby", [root.getAttribute("aria-describedby"), hint.id].filter(Boolean).join(" "));
      }
      list.setAttribute("role", "presentation");
      const showBadges = root.dataset.carouselBadges === "true";
      root.classList.toggle("pdk-carousel-badges", showBadges);
      if (showBadges && !["top-left", "top-right", "bottom-left", "bottom-right"].includes(root.dataset.carouselBadgeCorner)) root.dataset.carouselBadgeCorner = "top-right";
      cards.forEach((card, index) => {
        if (showBadges) {
          const badge = document.createElement("span");
          badge.className = "pdk-carousel-badge";
          badge.textContent = `${index + 1}/${cards.length}`;
          badge.setAttribute("aria-hidden", "true");
          card.append(badge);
          badges.push(badge);
        }
        card.setAttribute("role", "group");
        card.setAttribute("aria-roledescription", "slide");
        if (!card.hasAttribute("aria-label") && !card.hasAttribute("aria-labelledby")) card.setAttribute("aria-label", `${index + 1} of ${cards.length}`);
      });
      root.append(controls);
      root.classList.add("pdk-carousel-ready");
      root.classList.toggle("pdk-carousel-image-fill", root.dataset.carouselImageFill === "true");
      root.style.setProperty("--pdk-carousel-gap", `${gap}px`);
      on(root, "mouseenter", () => { hovered = true; schedule(); });
      on(root, "mouseleave", () => { hovered = false; schedule(); });
      on(root, "focusin", () => { focused = true; schedule(); });
      on(root, "focusout", event => { focused = root.contains(event.relatedTarget); schedule(); });
      on(root, "keydown", event => {
        if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
        if (event.target !== root && !controls.contains(event.target)) return;
        if (autoplay && event.key.toLowerCase() === "p") {
          if (atEnd()) return;
          event.preventDefault();
          paused = !paused;
          announcement.textContent = paused ? "Automatic rotation paused" : "Automatic rotation resumed";
          schedule();
          return;
        }
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault();
          move(event.key === "ArrowLeft" ? -1 : 1, true);
        }
      });
      on(root, "pointerdown", event => {
        if (cards.length <= visible || event.button !== 0 || !list.contains(event.target) || event.target.closest("button, input, textarea, select, [contenteditable]")) return;
        settle();
        pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, drag: 0, active: false, advanced: false};
        suppressClick = false;
        schedule();
      });
      on(root, "pointermove", event => {
        if (!pointer || pointer.id !== event.pointerId) return;
        let dx = event.clientX - pointer.x;
        const dy = event.clientY - pointer.y;
        if (!pointer.active && (Math.abs(dx) <= Math.abs(dy) || Math.abs(dx) < 8)) return;
        pointer.active = true;
        if (!root.hasPointerCapture(event.pointerId)) root.setPointerCapture(event.pointerId);
        // Rebase after each full card so dragging keeps following the pointer
        // through any number of cards, without exhausting the loop buffers.
        let advanced = false;
        while (stride > 0 && Math.abs(dx) >= stride) {
          const direction = dx < 0 ? 1 : -1;
          if (!loop && (direction < 0 ? start === 0 : atEnd())) break;
          if (cards.some(card => card.contains(document.activeElement))) root.focus({preventScroll: true});
          start = loop ? modulo(start + direction) : start + direction;
          pointer.x -= direction * stride;
          dx += direction * stride;
          advanced = pointer.advanced = true;
        }
        if (advanced) render();
        pointer.drag = Math.max(!loop && atEnd() ? 0 : -stride, Math.min(!loop && start === 0 ? 0 : stride, dx));
        if (pointer.drag !== dx) pointer.x = event.clientX - pointer.drag;
        suppressClick = true;
        root.classList.add("pdk-carousel-dragging");
        list.style.transform = `translateX(${offset + pointer.drag}px)`;
        event.preventDefault();
      });
      function release(event, cancelled = false) {
        if (!pointer || pointer.id !== event.pointerId) return;
        const drag = pointer.drag;
        const advanced = pointer.advanced;
        pointer = null;
        root.classList.remove("pdk-carousel-dragging");
        if (root.hasPointerCapture(event.pointerId)) root.releasePointerCapture(event.pointerId);
        if (!cancelled && Math.abs(drag) > Math.min(50, stride / 4)) move(drag < 0 ? 1 : -1, true, drag);
        else {
          list.style.transform = `translateX(${offset}px)`;
          if (advanced && !cancelled) announcement.textContent = position.textContent;
          schedule();
        }
      }
      on(root, "pointerup", event => release(event));
      on(root, "pointercancel", event => release(event, true));
      on(root, "lostpointercapture", event => { if (event.target === root) release(event, true); });
      on(root, "click", event => { if (suppressClick) { event.preventDefault(); suppressClick = false; } }, {capture: true});
      on(list, "dragstart", event => event.preventDefault());
      on(list, "load", event => { if (!event.target.closest("[data-pdk-carousel-clone]")) resize(); }, {capture: true});
      on(document, "visibilitychange", schedule);
      on(motion, "change", () => { settle(); schedule(); });
      on(window, "beforeprint", () => { printing = true; settle(); schedule(); });
      on(window, "afterprint", () => { printing = false; schedule(); });
      observer.observe(root);
      resize();
      document.fonts?.ready.then(() => { if (!listeners.signal.aborted) resize(); });
      return {destroy};
    } catch (error) {
      destroy();
      console.warn("Prodockit carousel kept its static grid:", error);
      return null;
    }
  }
  function refresh() {
    instances.forEach((instance, root) => {
      if (!root.isConnected) { instance.destroy(); instances.delete(root); }
    });
    if (!window.ResizeObserver || !window.AbortController || !("inert" in HTMLElement.prototype)) return;
    document.querySelectorAll(".grid.cards.pdk-carousel").forEach(root => {
      if (instances.has(root)) return;
      const instance = enhance(root);
      if (instance) instances.set(root, instance);
    });
  }
  if (typeof document$ !== "undefined") document$.subscribe(refresh);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", refresh);
  else refresh();
})();

// Optional viewport decorations. Configuration is emitted by pdk_festive().
(function () {
  "use strict";
  const artworkBase = document.currentScript?.src || location.href;
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const query = new URLSearchParams(location.search);
  const preview = loopback && query.get("pdk-festive-test") === "1";
  // Representatives for distinct Christmas offsets, including fractional zones.
  const stops = [
    ["Pacific/Kiritimati", "Kiritimati", "Kiribati"], ["Pacific/Chatham", "New Zealand", "NZ"],
    ["Pacific/Auckland", "New Zealand", "NZ"], ["Pacific/Fiji", "Fiji", "Fiji"],
    ["Australia/Sydney", "Sydney", "Sydney"], ["Australia/Adelaide", "Adelaide", "Adelaide"],
    ["Australia/Brisbane", "Brisbane", "Brisbane"], ["Australia/Darwin", "Darwin", "Darwin"],
    ["Asia/Tokyo", "Tokyo", "Tokyo"], ["Asia/Singapore", "Singapore", "SG"],
    ["Asia/Bangkok", "Bangkok", "Bangkok"], ["Asia/Yangon", "Myanmar", "Myanmar"],
    ["Asia/Dhaka", "Bangladesh", "Bangladesh"], ["Asia/Kathmandu", "Nepal", "Nepal"],
    ["Asia/Kolkata", "Delhi", "Delhi"], ["Asia/Karachi", "Karachi", "Karachi"],
    ["Asia/Kabul", "Kabul", "Kabul"], ["Asia/Dubai", "Dubai", "Dubai"],
    ["Asia/Tehran", "Tehran", "Tehran"], ["Asia/Riyadh", "Riyadh", "Riyadh"],
    ["Europe/Athens", "Athens", "Athens"], ["Europe/Paris", "Paris", "Paris"],
    ["Europe/London", "London", "London"], ["Atlantic/Azores", "Azores", "Azores"],
    ["Atlantic/South_Georgia", "South Georgia", "S Georgia"], ["America/Sao_Paulo", "Rio", "Rio"],
    ["America/St_Johns", "Newfoundland", "Newfoundl."], ["America/Halifax", "Nova Scotia", "Nova Scotia"],
    ["America/New_York", "New York", "NY"], ["America/Chicago", "Chicago", "Chicago"],
    ["America/Denver", "Denver", "Denver"], ["America/Los_Angeles", "Los Angeles", "LA"],
    ["America/Anchorage", "Alaska", "Alaska"], ["Pacific/Marquesas", "Marquesas", "Marquesas"],
    ["Pacific/Honolulu", "Hawaii", "Hawaii"], ["Pacific/Pago_Pago", "American Samoa", "Am. Samoa"],
    ["Etc/GMT+12", "Baker Island", "Baker Is."]
  ];
  const schedules = new Map();
  function schedule(year) {
    if (schedules.has(year)) return schedules.get(year);
    const midnight = Date.UTC(year, 11, 25);
    const result = stops.map(([zone, label, compact]) => {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: zone, timeZoneName: "longOffset"
      }).formatToParts(new Date(midnight));
      const offset = parts.find(p => p.type === "timeZoneName").value;
      const match = offset.match(/GMT([+-])(\d{2}):(\d{2})/);
      const minutes = match ? (Number(match[2]) * 60 + Number(match[3])) * (match[1] === "+" ? 1 : -1) : 0;
      return {time: midnight - minutes * 60000, label, compact};
    }).sort((a, b) => a.time - b.time);
    schedules.clear();
    schedules.set(year, result);
    return result;
  }
  function destination(time) {
    const date = new Date(time), year = date.getUTCFullYear();
    if (time < Date.UTC(year, 11, 24, 10) || time >= Date.UTC(year, 11, 26, 12)) return null;
    return schedule(year).filter(stop => stop.time <= time).at(-1);
  }
  function day(value) {
    if (typeof value !== "string" || !/^\d{2}-\d{2}$/.test(value)) throw Error("season dates must use MM-DD");
    const date = new Date("2000-" + value + "T00:00:00Z");
    if (!Number.isFinite(+date) || date.toISOString().slice(5, 10) !== value) throw Error("invalid season date");
    return value;
  }
  let controller;
  function start() {
    const marker = document.querySelector("[data-pdk-festive]");
    if (!marker && !preview) { controller?.dispose(); controller = null; return; }
    const raw = marker?.getAttribute("data-pdk-festive") || "{}";
    const automaticDay = new Date().getMonth() === 0 && new Date().getDate() === 1;
    const signature = raw + ":" + automaticDay;
    if (controller?.signature === signature) { controller.mountToggle(); return; }
    controller?.dispose();
    controller = null;
    try {
      const config = JSON.parse(raw);
      if (config.enabled !== true && !preview) return;
      if (config.effect && !["snow", "fireworks", "auto"].includes(config.effect)) throw Error("effect must be snow, fireworks or auto");
      for (const key of ["enabled", "sleigh"]) {
        if (config[key] !== undefined && typeof config[key] !== "boolean") throw Error(key + " must be a boolean");
      }
      const first = day(config.season_start || "12-01"), last = day(config.season_end || "01-06");
      const requested = preview && query.get("pdk-festive-effect") || config.effect || "snow";
      const now = new Date();
      const fireworks = requested === "fireworks" ||
        (requested === "auto" && now.getMonth() === 0 && now.getDate() === 1);
      controller = fireworks ? createFireworks(config, raw) : create(config, first, last, raw);
      controller.signature = signature;
    } catch (error) { console.warn("Prodockit festive overlay:", error.message); }
  }
  function createFireworks(config, raw) {
    const events = new AbortController();
    const on = (el, type, action) => el.addEventListener(type, action, {signal: events.signal});
    const canvas = document.createElement("canvas");
    canvas.className = "pdk-festive-canvas"; canvas.setAttribute("aria-hidden", "true");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw Error("canvas is unavailable");
    const controls = document.createElement("div"); controls.className = "pdk-festive-controls";
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let paused = motion.matches, hidden = false, printing = false, sound = false;
    let audio, volume = 0.25, master, frame = 0, previous = 0, launchIn = 0;
    let width = innerWidth, height = innerHeight, rockets = [], sparks = [], groundEffects = [];
    let seed = Number(query.get("pdk-festive-seed") || 42) >>> 0;
    let simulated = preview && query.get("pdk-festive-time") ? Date.parse(query.get("pdk-festive-time")) : Date.now();
    if (!Number.isFinite(simulated)) throw Error("invalid fireworks preview time");
    let speed = preview ? Number(query.get("pdk-festive-speed") || 1) : 1;
    if (!Number.isFinite(speed) || speed < 0 || speed > 3600) throw Error("invalid preview speed");
    const zone = preview && query.get("pdk-festive-zone") || Intl.DateTimeFormat().resolvedOptions().timeZone;
    const formatter = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    });
    function active() {
      const parts = Object.fromEntries(formatter.formatToParts(new Date(preview ? simulated : Date.now())).map(p => [p.type, p.value]));
      return parts.month === "01" && parts.day === "01" && Number(parts.hour) < 2;
    }
    function random() { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; }
    function button(text, label, action, parent = controls) {
      const el = document.createElement("button"); el.type = "button"; el.textContent = text;
      el.setAttribute("aria-label", label); on(el, "click", action); parent.append(el); return el;
    }
    function outlineIcon(paths) {
      return '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths + '</svg>';
    }
    const fireworkIcon = outlineIcon('<path d="M12 3v4m0 6v8M3 10h4m10 0h4M5.6 3.6l2.8 2.8m7.2 0 2.8-2.8M5.6 16.4l2.8-2.8m7.2 0 2.8 2.8"/><circle cx="12" cy="10" r="1.5"/>');
    const speakerBody = '<path d="M11 5 6 9H3v6h3l5 4z"/>';
    const speakerOnIcon = outlineIcon(speakerBody + '<path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>');
    const speakerOffIcon = outlineIcon(speakerBody + '<path d="m16 9 5 6m0-6-5 6"/>');
    const toggle = button("", "Turn fireworks off", () => { hidden = !hidden; refresh(); });
    toggle.className = "pdk-festive-toggle md-header__button md-icon";
    toggle.innerHTML = fireworkIcon;
    const speaker = button("", "Enable fireworks sound", async () => {
      if (!sound) {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) { speaker.disabled = true; speaker.title = "Audio is unavailable"; return; }
        try {
          if (!audio) {
            audio = new Audio(); master = audio.createGain(); master.gain.value = 0;
            master.connect(audio.destination);
          }
          await audio.resume();
          if (events.signal.aborted) return;
          sound = true;
        } catch (_) { return; }
      } else sound = false;
      refresh();
    });
    speaker.className = "pdk-festive-speaker md-header__button md-icon";
    function mountToggle() {
      const palette = document.querySelector("[data-md-component=palette]");
      if (palette) { palette.before(toggle); palette.before(speaker); }
    }
    const pause = button("Pause fireworks", "Pause fireworks", () => { paused = !paused; refresh(); });
    const level = document.createElement("input");
    level.type = "range"; level.min = "0"; level.max = "100"; level.value = "25";
    level.setAttribute("aria-label", "Fireworks volume");
    on(level, "input", () => { volume = Number(level.value) / 100; syncAudio(); });
    controls.append(level);
    const styles = ["Peony", "Ring", "Palm", "Willow", "Crackle", "Roman candle bank", "Fountain", "Fan jets", "Mine"];
    let chosen = "Mixed", pendingKind = null, status;
    if (preview) {
      const select = document.createElement("select"); select.setAttribute("aria-label", "Fireworks style");
      for (const label of ["Mixed", ...styles]) {
        const option = document.createElement("option"); option.textContent = label; select.append(option);
      }
      on(select, "change", () => {
        chosen = select.value; pendingKind = null; launchIn = 0; rockets = []; sparks = []; groundEffects = [];
      }); controls.append(select);
      const clock = document.createElement("input"); clock.type = "datetime-local";
      clock.value = new Date(simulated).toISOString().slice(0, 19); clock.setAttribute("aria-label", "Simulated UTC time");
      on(clock, "change", () => {
        const next = Date.parse(clock.value + "Z");
        if (Number.isFinite(next)) { simulated = next; rockets = []; sparks = []; groundEffects = []; refresh(); }
      }); controls.append(clock);
      const rate = document.createElement("input"); rate.type = "number"; rate.min = "0"; rate.max = "3600";
      rate.value = String(speed); rate.setAttribute("aria-label", "Clock speed");
      on(rate, "change", () => { const next = Number(rate.value); if (Number.isFinite(next) && next >= 0 && next <= 3600) speed = next; });
      controls.append(rate);
      button("Burst", "Launch a test firework", () => { if (active()) launch(); draw(); });
      button("Step", "Advance fireworks one frame", () => { advance(1 / 60); draw(); });
      button("Reset", "Reset fireworks", () => { seed = 42; pendingKind = null; rockets = []; sparks = []; groundEffects = []; launchIn = 0; draw(); });
      status = document.createElement("output"); controls.append(status);
    }
    function syncAudio() {
      if (!master) return;
      const audible = sound && !paused && !hidden && !document.hidden && !printing && active();
      master.gain.setTargetAtTime(audible ? volume * 0.35 : 0, audio.currentTime, 0.02);
    }
    function noise(duration, low, delay = 0) {
      if (!sound || !audio || audio.state !== "running" || document.hidden || paused || hidden || !active()) return;
      const buffer = audio.createBuffer(1, Math.ceil(audio.sampleRate * duration), audio.sampleRate);
      const samples = buffer.getChannelData(0);
      for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;
      const source = audio.createBufferSource(), filter = audio.createBiquadFilter(), gain = audio.createGain();
      source.buffer = buffer; filter.type = "lowpass"; filter.frequency.value = low;
      const when = audio.currentTime + delay;
      gain.gain.setValueAtTime(1, when); gain.gain.exponentialRampToValueAtTime(0.001, when + duration);
      source.connect(filter); filter.connect(gain); gain.connect(master);
      source.onended = () => { source.disconnect(); filter.disconnect(); gain.disconnect(); };
      source.start(when); source.stop(when + duration);
    }
    function launch() {
      if (groundEffects.length || sparks.some(p => p.ground) || rockets.length >= 5 || sparks.length > 1000) return;
      // Keep a selected ground sequence queued while the aerial display clears.
      // Rerolling here allowed new aerial launches to starve ground effects.
      if (!pendingKind) pendingKind = chosen === "Mixed" ? styles[Math.floor(random() * styles.length)] : chosen;
      const kind = pendingKind;
      if (["Roman candle bank", "Fountain", "Fan jets", "Mine"].includes(kind)) {
        if (rockets.length || sparks.length) return;
        if (groundEffects.length === 0) {
          pendingKind = null;
          const hue = random() * 360;
          for (let i = 0; i < 3; i++) {
            groundEffects.push({kind, x: width * (0.2 + i * 0.3), life: kind === "Mine" ? 0.1 : 5,
              next: 0, hue: (hue + i * 120) % 360, volley: 0});
          }
        }
        return;
      }
      pendingKind = null;
      const count = Math.min(1 + Math.floor(random() * 3), 5 - rockets.length);
      const target = height * (0.15 + random() * 0.35);
      const hue = random() * 360;
      for (let i = 0; i < count; i++) {
        rockets.push({
          x: width * (count === 1 ? 0.2 + random() * 0.6 : 0.2 + i * 0.6 / (count - 1)),
          y: height + 5, target, hue: (hue + i * 120) % 360, kind
        });
      }
      noise(0.35, 1600);
    }
    function burst(rocket) {
      const count = rocket.kind === "Palm" ? 35 : 90;
      for (let i = 0; i < count && sparks.length < 1400; i++) {
        const angle = i / count * Math.PI * 2;
        const radius = rocket.kind === "Ring" ? 100 : 35 + random() * 100;
        const a = rocket.kind === "Palm" ? -Math.PI + random() * Math.PI : angle;
        sparks.push({x: rocket.x, y: rocket.y, px: rocket.x, py: rocket.y,
          vx: Math.cos(a) * radius, vy: Math.sin(a) * radius,
          life: rocket.kind === "Willow" ? 4 : 1.5 + random() * 1.5,
          hue: rocket.kind === "Willow" ? 42 : rocket.hue, kind: rocket.kind});
      }
      noise(0.9, 250, 0.12);
      if (rocket.kind === "Crackle") for (let i = 0; i < 6; i++) noise(0.07, 3000, 0.3 + i * 0.1);
    }
    function erupt(effect) {
      const roman = effect.kind === "Roman candle bank";
      const mine = effect.kind === "Mine";
      const jets = effect.kind === "Fan jets" ? 7 : roman ? 5 : 1;
      const perJet = mine ? 100 : roman ? 4 : 12;
      for (let tube = 0; tube < jets; tube++) {
        const direction = -Math.PI / 2 + (effect.kind === "Fan jets" ? (tube - 3) * 0.16 : 0);
        const x = effect.x + (tube - (jets - 1) / 2) * Math.min(24, width / 20);
        for (let i = 0; i < perJet && sparks.length < 1400; i++) {
          const angle = direction + (random() - 0.5) * (mine ? 1.1 : 0.18);
          const velocity = roman ? 190 + random() * 80 : mine ? 100 + random() * 250 : 100 + random() * 140;
          sparks.push({x, y: height - 3, px: x, py: height - 3,
            vx: Math.cos(angle) * velocity, vy: Math.sin(angle) * velocity,
            life: roman ? 3.5 : 1.5 + random() * 1.7,
            hue: (effect.hue + (random() - 0.5) * 12 + 360) % 360,
            kind: effect.kind, ground: true});
        }
      }
      effect.volley++;
      noise(roman ? 0.14 : mine ? 0.6 : 0.2, roman ? 900 : 2400);
    }
    function advance(dt) {
      if (preview) simulated += dt * speed * 1000;
      if (!active()) { rockets = []; sparks = []; groundEffects = []; return; }
      launchIn -= dt;
      if (launchIn <= 0) { launch(); launchIn = 1.2 + random() * 1.6; }
      groundEffects = groundEffects.filter(effect => {
        effect.life -= dt; effect.next -= dt;
        if (effect.next <= 0) {
          erupt(effect);
          effect.next = effect.kind === "Roman candle bank" ? 0.65 : 0.09;
        }
        return effect.life > 0;
      });
      rockets = rockets.filter(r => {
        r.y -= dt * 250;
        if (r.y <= r.target) { burst(r); return false; } return true;
      });
      sparks = sparks.filter(p => {
        p.px = p.x; p.py = p.y;
        p.x += p.vx * dt; p.y += p.vy * dt; p.vy += dt * (p.ground ? 95 : p.kind === "Willow" ? 19 : 35);
        p.vx *= Math.exp(-dt * 0.25); p.life -= dt; return p.life > 0 && (!p.ground || p.y < height + 8);
      });
    }
    function draw() {
      ctx.clearRect(0, 0, width, height);
      if (active()) {
        for (const r of rockets) {
          ctx.strokeStyle = "hsl(" + r.hue + " 85% 55%)"; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(r.x, r.y + 18); ctx.lineTo(r.x, r.y); ctx.stroke();
        }
        for (const p of sparks) {
          ctx.globalAlpha = Math.min(1, p.life);
          ctx.strokeStyle = "hsl(" + p.hue + " 90% 55%)"; ctx.lineWidth = p.kind === "Willow" ? 1.3 : 2;
          ctx.beginPath(); ctx.moveTo(p.px, p.py); ctx.lineTo(p.x, p.y); ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
      if (status) status.textContent = new Date(simulated).toISOString() + " · " + zone +
        " · " + (active() ? "New Year active" : "Outside 00:00–02:00 on 1 January") + " · " + sparks.length + " sparks";
      if (preview) canvas.dataset.snapshot = JSON.stringify({effect: "fireworks", active: active(), sparks: sparks.length,
        rockets: rockets.length, groundEffects: groundEffects.map(e => e.kind), groundSparks: sparks.filter(p => p.ground).length, sound, paused, hidden, zone, style: chosen});
    }
    function tick(now) {
      frame = 0; const dt = Math.min(0.05, previous ? (now - previous) / 1000 : 0); previous = now;
      advance(dt); draw(); syncAudio();
      frame = requestAnimationFrame(tick);
    }
    function refresh() {
      cancelAnimationFrame(frame); frame = 0; previous = 0;
      canvas.hidden = hidden; controls.hidden = !preview && !active();
      toggle.setAttribute("aria-pressed", String(!hidden));
      toggle.setAttribute("aria-label", hidden ? "Turn fireworks on" : "Turn fireworks off");
      speaker.innerHTML = sound ? speakerOnIcon : speakerOffIcon;
      speaker.setAttribute("aria-label", sound ? "Mute fireworks sound" : "Enable fireworks sound");
      speaker.setAttribute("aria-pressed", String(sound));
      pause.textContent = paused ? "Resume fireworks" : "Pause fireworks";
      mountToggle(); draw(); syncAudio();
      if (!hidden && !paused && !document.hidden && !printing) frame = requestAnimationFrame(tick);
    }
    function resize() {
      width = Math.max(1, innerWidth); height = Math.max(1, innerHeight);
      const ratio = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0); draw();
    }
    document.body.append(canvas, controls); resize();
    on(window, "resize", resize); on(document, "visibilitychange", refresh);
    on(motion, "change", () => { if (motion.matches) paused = true; refresh(); });
    on(window, "beforeprint", () => { printing = true; refresh(); });
    on(window, "afterprint", () => { printing = false; refresh(); });
    const timer = setInterval(() => { start(); if (!events.signal.aborted) refresh(); }, 60000);
    refresh();
    return {raw, mountToggle, dispose() {
      events.abort(); clearInterval(timer); cancelAnimationFrame(frame);
      audio?.close(); canvas.remove(); controls.remove(); toggle.remove(); speaker.remove();
    }};
  }
  function create(config, first, last, raw) {
    const events = new AbortController();
    const on = (target, type, action) => target.addEventListener(type, action, {signal: events.signal});
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const canvas = document.createElement("canvas");
    canvas.className = "pdk-festive-canvas";
    canvas.setAttribute("aria-hidden", "true");
    const controls = document.createElement("div");
    controls.className = "pdk-festive-controls";
    controls.setAttribute("aria-label", "Festive effects");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw Error("canvas is unavailable");
    let artwork;
    function loadArtwork() {
      if (artwork) return;
      artwork = new Image();
      artwork.onload = () => { if (!events.signal.aborted) draw(); };
      artwork.src = new URL("pdk-sleigh.png", artworkBase).href;
    }
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem("pdk-festive") || "{}") || {}; } catch (_) {}
    let paused = motion.matches || saved.paused === true, hidden = saved.hidden === true;
    let printing = false, frame = 0, previous = 0, angle = 0, width = Math.max(1, innerWidth), height = Math.max(1, innerHeight);
    let particles = [], bank = [], seed = 42;
    const seedInput = Number(query.get("pdk-festive-seed") || 42);
    const initialSeed = Number.isFinite(seedInput) ? seedInput >>> 0 : 42;
    let simulated = Date.now(), speed = 1, liveSantaZone = false, frames = 0, frameCost = 0, density = 1;
    if (preview) {
      const value = query.get("pdk-festive-time");
      if (value && !/Z$/.test(value)) throw Error("preview time must be an ISO UTC timestamp ending in Z");
      simulated = value ? Date.parse(value) : Date.now();
      speed = Number(query.get("pdk-festive-speed") || 1);
      if (!Number.isFinite(simulated) || !Number.isFinite(speed) || speed < 0 || speed > 3600) throw Error("invalid preview time or speed");
    }
    function random() { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; }
    let flight;
    let meltPatches = [], meltTimer = 0;
    function newFlight() {
      flight = {
        progress: 0, fromLeft: random() < 0.5,
        startY: 0.15 + random() * 0.65, endY: 0.15 + random() * 0.65,
        bend: (random() - 0.5) * 0.16
      };
    }
    function reset() {
      seed = initialSeed; bank = Array(Math.min(1600, Math.ceil(width / 3))).fill(0); angle = 0;
      particles = Array.from({length: Math.min(180, Math.ceil(width / 4))}, () => ({
        x: random() * width, y: random() * height,
        r: 1 + random() * 2, v: 22 + random() * 40, phase: random() * 6.28
      }));
      meltPatches = []; meltTimer = 0;
      newFlight();
    }
    function persist() { try { localStorage.setItem("pdk-festive", JSON.stringify({paused, hidden})); } catch (_) {} }
    function button(label, action) {
      const element = document.createElement("button");
      element.type = "button"; element.textContent = label;
      on(element, "click", action); controls.append(element); return element;
    }
    const pause = button("", () => { paused = !paused; persist(); refresh(); });
    const hide = button("", () => { hidden = !hidden; persist(); refresh(); });
    const toggle = document.createElement("button");
    toggle.type = "button"; toggle.className = "pdk-festive-toggle md-header__button md-icon";
    toggle.textContent = "❄"; toggle.setAttribute("aria-label", "Turn festive mode off");
    on(toggle, "click", () => { hidden = !hidden; persist(); refresh(); });
    function mountToggle() {
      const palette = document.querySelector("[data-md-component=palette]");
      if (palette && toggle.nextElementSibling !== palette) palette.before(toggle);
      else if (!palette && !toggle.isConnected) controls.prepend(toggle);
    }
    let panel, status, clock;
    if (preview) {
      panel = document.createElement("div"); panel.className = "pdk-festive-preview";
      controls.append(panel);
      const title = document.createElement("strong"); title.textContent = "Festive preview"; panel.append(title);
      clock = document.createElement("input"); clock.type = "datetime-local"; clock.setAttribute("aria-label", "Simulated UTC time");
      clock.value = new Date(simulated).toISOString().slice(0, 19);
      on(clock, "change", () => { const value = Date.parse(clock.value + "Z"); if (Number.isFinite(value)) { liveSantaZone = false; simulated = value; } draw(); });
      panel.append(clock);
      const rate = document.createElement("input"); rate.type = "number"; rate.min = "0"; rate.max = "3600"; rate.value = String(speed);
      rate.setAttribute("aria-label", "Clock speed");
      on(rate, "change", () => { const value = Number(rate.value); if (Number.isFinite(value) && value >= 0 && value <= 3600) { liveSantaZone = false; speed = value; } });
      panel.append(rate);
      button("Step", () => { advance(1 / 60); draw(); });
      button("Reset snow", () => { reset(); draw(); });
      const preset = document.createElement("select"); preset.setAttribute("aria-label", "Preview preset");
      for (const text of ["Choose preset", "Reset", "Changing Location", "Current Santa zone", "Christmas start", "Nepal", "Christmas end", "Maximum snow", "Light palette", "Dark palette", "Reduced motion"]) {
        const option = document.createElement("option"); option.textContent = text; preset.append(option);
      }
      on(preset, "change", () => {
        const year = new Date(simulated).getUTCFullYear();
        liveSantaZone = preset.value === "Current Santa zone";
        if (preset.value === "Reset") {
          reset();
          simulated = query.get("pdk-festive-time")
            ? Date.parse(query.get("pdk-festive-time")) : Date.now();
          speed = Number(query.get("pdk-festive-speed") || 1);
          paused = motion.matches; hidden = false;
          rate.value = String(speed);
        }
        if (preset.value === "Changing Location") {
          simulated = schedule(year)[0].time;
          speed = 0; rate.value = "0"; paused = false; hidden = false;
          newFlight();
        }
        if (liveSantaZone) {
          const now = new Date();
          simulated = Date.UTC(year, 11, 25, now.getUTCHours(), now.getUTCMinutes(), now.getUTCSeconds());
          speed = 1; rate.value = "1";
        }
        const times = {"Christmas start": Date.UTC(year, 11, 24, 10), Nepal: Date.UTC(year, 11, 24, 18, 15), "Christmas end": Date.UTC(year, 11, 26, 12)};
        if (times[preset.value] !== undefined) simulated = times[preset.value];
        if (preset.value === "Maximum snow") bank.fill(48);
        if (preset.value === "Reduced motion") paused = true;
        if (preset.value.includes("palette")) {
          const scheme = preset.value === "Dark palette" ? "slate" : "default";
          document.querySelector('[data-md-color-scheme="' + scheme + '"][type="radio"]')?.click();
        }
        clock.value = new Date(simulated).toISOString().slice(0, 19); refresh();
      });
      panel.append(preset);
      status = document.createElement("output"); panel.append(status);
    }
    function eligible() {
      if (preview) return true;
      const today = new Date().toISOString().slice(5, 10);
      return first <= last ? today >= first && today <= last : today >= first || today <= last;
    }
    function resize() {
      width = Math.max(1, window.innerWidth); height = Math.max(1, window.innerHeight);
      const ratio = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      particles.forEach(p => { p.x %= width; p.y %= height; });
      const previousBank = bank;
      const count = Math.min(1600, Math.ceil(width / 3));
      bank = Array.from({length: count}, (_, i) =>
        previousBank[Math.min(previousBank.length - 1, Math.floor(i / count * previousBank.length))] || 0);
      draw();
    }
    function advance(dt) {
      if (preview) {
        if (liveSantaZone) {
          const now = new Date();
          simulated = Date.UTC(new Date(simulated).getUTCFullYear(), 11, 25,
            now.getUTCHours(), now.getUTCMinutes(), now.getUTCSeconds(), now.getUTCMilliseconds());
          clock.value = new Date(simulated).toISOString().slice(0, 19);
        } else simulated += dt * speed * 1000;
      }
      angle += dt * 0.12;
      flight.progress += dt * 55 / (width + 320);
      // Both endpoints are beyond the rotated artwork bounds. Pick the next
      // entrance only after the complete sleigh and parcel sled have left.
      if (flight.progress >= 1) {
        if (preview && !liveSantaZone && config.sleigh !== false) {
          const year = new Date(simulated).getUTCFullYear();
          const route = schedule(year);
          const currentLabel = destination(simulated)?.label;
          const next = route.find(stop => stop.time > simulated && stop.label !== currentLabel);
          const firstDifferent = route.find(stop => stop.label !== currentLabel);
          simulated = (next || firstDifferent || route[0]).time;
          clock.value = new Date(simulated).toISOString().slice(0, 19);
        }
        newFlight();
      }
      // Thaw a few small patches at a time, leaving other areas to form drifts.
      meltTimer -= dt;
      if (meltTimer <= 0) {
        meltTimer = 4 + random() * 4;
        meltPatches = Array.from({length: 3}, () => ({
          centre: random(), radius: 0.025 + random() * 0.025
        }));
      }
      for (let i = 0; i < bank.length; i++) {
        const position = (i + 0.5) / bank.length;
        for (const patch of meltPatches) {
          const distance = Math.abs(position - patch.centre);
          if (distance < patch.radius) {
            const strength = 1 - distance / patch.radius;
            bank[i] = Math.max(0, bank[i] - dt * 1.8 * strength);
          }
        }
      }
      for (const p of particles) {
        p.y += p.v * dt; p.x = (p.x + Math.sin(angle + p.phase) * dt * 12 + width) % width;
        const index = Math.min(bank.length - 1, Math.floor(p.x / width * bank.length));
        if (p.y + p.r >= height - bank[index]) {
          // Deposit across the flake's own footprint, instead of a wide column.
          const left = Math.max(0, Math.floor((p.x - p.r) / width * bank.length));
          const right = Math.min(bank.length - 1, Math.floor((p.x + p.r) / width * bank.length));
          for (let i = left; i <= right; i++) bank[i] = Math.min(48, bank[i] + p.r * 1.6);
          // Recycle immediately so the population never exhausts and pauses.
          p.x = random() * width; p.y = -p.r;
        }
      }
    }
    function draw() {
      ctx.clearRect(0, 0, width, height);
      const dark = document.body.getAttribute("data-md-color-scheme") === "slate" ||
        (document.body.getAttribute("data-md-color-scheme") === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
      const colour = dark ? "#fff" : "#111";
      ctx.fillStyle = colour;
      for (const p of particles.slice(0, Math.ceil(particles.length * density))) { ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill(); }
      for (let i = 0; i < bank.length; i++) ctx.fillRect(i * width / bank.length, height - bank[i], width / bank.length + 0.25, bank[i]);
      const stop = config.sleigh === false ? null : destination(preview ? simulated : Date.now());
      if (stop) sleigh(stop);
      if (status) status.textContent = new Date(simulated).toISOString() + " · " + (stop?.label || "No sleigh") +
        " · " + (dark ? "dark" : "light") + " · " + particles.length + " flakes · " + Math.max(...bank).toFixed(1) +
        " px snow · " + frameCost.toFixed(1) + " ms/frame";
      if (preview) canvas.dataset.snapshot = JSON.stringify({particles: particles.length, bank: Math.max(...bank), destination: stop?.label, colour, paused, hidden});
    }
    function sleigh(stop) {
      loadArtwork();
      if (!artwork.complete || !artwork.naturalWidth) return;
      const spriteWidth = Math.min(240, width - 24, (height - 120) * 1.5);
      const spriteHeight = spriteWidth * artwork.naturalHeight / artwork.naturalWidth;
      const progress = flight.progress;
      const centreX = flight.fromLeft
        ? -160 + (width + 320) * progress
        : width + 160 - (width + 320) * progress;
      const centreY = height * (
        flight.startY + (flight.endY - flight.startY) * progress +
        flight.bend * Math.sin(Math.PI * progress)
      );
      const velocityY = height * (
        flight.endY - flight.startY + flight.bend * Math.PI * Math.cos(Math.PI * progress)
      );
      const facingLeft = !flight.fromLeft;
      const pitch = Math.max(-0.38, Math.min(0.38,
        Math.atan2(velocityY, width + 320))) * (facingLeft ? -1 : 1);
      ctx.save();
      ctx.translate(centreX, centreY);
      ctx.rotate(pitch);
      ctx.save();
      if (facingLeft) ctx.scale(-1, 1);
      ctx.drawImage(artwork, -spriteWidth / 2, -spriteHeight / 2, spriteWidth, spriteHeight);
      ctx.restore();
      // Draw destination text separately so the left-facing version stays readable.
      const plaqueCentre = spriteWidth * 0.02 * (facingLeft ? -1 : 1);
      ctx.fillStyle = "#301b15";
      const fontSize = spriteWidth * 0.052;
      const labelWidth = spriteWidth * 0.55;
      ctx.font = "bold " + fontSize + "px sans-serif";
      const label = ctx.measureText(stop.label).width <= labelWidth ? stop.label : stop.compact;
      const fittedSize = fontSize * Math.min(1, labelWidth / ctx.measureText(label).width);
      ctx.font = "bold " + fittedSize + "px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, plaqueCentre, spriteHeight * 0.145);
      ctx.restore();
    }
    function tick(now) {
      frame = 0;
      const begin = performance.now(), dt = Math.min(0.05, previous ? (now - previous) / 1000 : 0);
      previous = now; advance(dt); draw();
      frameCost = frameCost * 0.95 + (performance.now() - begin) * 0.05;
      if (++frames % 300 === 0) density = frameCost > 12 ? Math.max(0.25, density * 0.8) : Math.min(1, density + 0.05);
      frame = requestAnimationFrame(tick);
    }
    function refresh() {
      cancelAnimationFrame(frame); frame = 0; previous = 0;
      canvas.hidden = hidden || !eligible(); controls.hidden = !eligible();
      pause.textContent = paused ? "Resume snow" : "Pause snow"; pause.setAttribute("aria-pressed", String(paused));
      mountToggle();
      toggle.setAttribute("aria-pressed", String(!hidden));
      toggle.setAttribute("aria-label", hidden ? "Turn festive mode on" : "Turn festive mode off");
      toggle.title = hidden ? "Turn festive mode on" : "Turn festive mode off";
      hide.textContent = hidden ? "Show snow" : "Hide snow"; hide.setAttribute("aria-pressed", String(hidden));
      draw();
      if (!hidden && eligible() && !paused && !document.hidden && !printing) frame = requestAnimationFrame(tick);
    }
    reset(); document.body.append(canvas, controls); resize();
    on(window, "resize", resize);
    if (window.visualViewport) on(window.visualViewport, "resize", resize);
    on(document, "visibilitychange", refresh);
    on(motion, "change", () => { if (motion.matches) paused = true; refresh(); });
    on(window, "beforeprint", () => { printing = true; refresh(); });
    on(window, "afterprint", () => { printing = false; refresh(); });
    const observer = new MutationObserver(draw);
    observer.observe(document.body, {attributes: true, attributeFilter: ["data-md-color-scheme"]});
    const timer = setInterval(() => { start(); if (!events.signal.aborted) refresh(); }, 60000);
    refresh();
    return {raw, mountToggle, dispose() { events.abort(); observer.disconnect(); clearInterval(timer); cancelAnimationFrame(frame); canvas.remove(); controls.remove(); toggle.remove(); }};
  }
  if (typeof document$ !== "undefined") document$.subscribe(start);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
