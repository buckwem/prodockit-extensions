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
      for (const key of ["enabled", "sleigh", "drone"]) {
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
  // Surface samples from Quaternius’s CC0 Deer, https://poly.pizza/m/T6Cs7tmMHJ
  const droneDeerSurface = [[0.6068,0.8462,-0.0642],[0.198,0.4361,0.0738],[0.1364,1.0777,-0.0623],[0.5765,0.1704,-0.0042],[0.6971,-0.1789,0.0795],[0.6109,1.2149,0.0686],[0.5436,0.5152,-0.0806],[0.5946,1.0755,-0.046],[0.6401,0.5489,-0.0063],[0.1891,0.6632,0.0739],[0.5466,0.201,0.0568],[0.711,-0.1544,-0.0681],[0.3658,0.324,-0.0728],[0.1799,0.6694,-0.062],[0.2099,0.2262,0.0133],[0.482,0.3223,0.073],[0.6887,-0.1153,0.0563],[0.1876,0.5884,0.0473],[0.2708,0.5664,-0.0892],[0.3603,0.2504,-0.0615],[0.5404,0.5843,-0.067],[0.6709,0.2514,0.0467],[0.1921,1.2274,0.0592],[0.7024,0.1969,-0.0341],[0.6049,0.893,-0.0647],[0.6842,-0.2047,-0.119],[0.2116,0.6793,0.0795],[0.6286,0.5761,0.0228],[0.5906,0.7325,-0.037],[0.5278,0.5184,-0.0729],[0.5707,0.4126,-0.0795],[0.1756,1.2283,0.0432],[0.5111,0.1869,0.0339],[0.5477,0.1764,0.0455],[0.2352,0.712,0.0559],[0.7292,0.2028,-0.0086],[0.6256,0.5798,-0.0386],[0.1591,0.7162,0.0534],[0.497,0.3753,0.0737],[0.2532,0.223,-0.0491],[0.1904,0.4302,0.0668],[0.1998,0.7249,-0.0756],[0.6427,0.1622,-0.0417],[0.5158,0.4564,0.0707],[0.2038,0.7247,-0.0739],[0.244,0.3867,-0.0952],[0.551,0.5569,0.0825],[0.2918,0.5075,0.0916],[0.5377,0.4523,-0.0778],[0.7292,0.1818,-0.0136],[0.5275,0.6007,-0.0383],[0.3188,0.6063,0.016],[0.6026,1.0716,-0.0536],[0.262,0.1985,-0.0157],[0.6405,0.5082,-0.0552],[0.5795,0.8956,-0.0689],[0.2673,0.6154,0.0803],[0.4599,0.6032,0.0497],[0.7332,0.1815,-0.006],[0.4136,0.6284,-0.0299],[0.2676,0.2099,-0.0448],[0.2261,0.7157,0.0631],[0.2473,0.5951,0.0877],[0.6162,0.6264,-0.0602],[0.4049,0.5568,-0.0693],[0.6814,-0.1747,0.1055],[0.6795,-0.1943,0.0874],[0.2227,0.2596,0.0628],[0.6824,0.4028,0.0224],[0.2058,0.3884,0.0838],[0.4112,0.4996,0.0738],[0.5948,0.8944,0.069],[0.1714,1.042,-0.0629],[0.3285,0.5889,0.0378],[0.1788,0.4863,0.0192],[0.1846,0.3433,0.0628],[0.2134,0.2273,0.028],[0.3325,0.2628,-0.069],[0.687,-0.1929,0.076],[0.5902,1.0074,-0.0675],[0.2373,0.2084,-0.0017],[0.6078,0.9071,0.0555],[0.2002,0.2422,-0.0159],[0.2104,0.5419,-0.0201],[0.1654,0.4075,0.0131],[0.7448,0.0319,0.0121],[0.6949,0.2916,-0.0338],[0.2041,0.7525,0.069],[0.1852,0.5731,-0.0271],[0.1662,0.8753,0.0731],[0.5779,0.742,-0.0395],[0.5228,0.179,-0.0381],[0.2791,0.2335,0.0635],[0.607,0.5362,0.0779],[0.3279,0.5478,0.0706],[0.3428,0.2368,-0.0562],[0.7792,-0.0654,0.0363],[0.7224,0.2169,0.0165],[0.2536,0.5709,-0.0124],[0.8543,-0.0598,-0.012],[0.7202,0.0523,-0.0296],[0.5896,0.186,-0.0424],[0.4924,0.5611,0.0632],[0.1721,1.2057,0.0712],[0.6027,0.9268,-0.063],[0.6472,0.2218,-0.0508],[0.2332,0.6496,0.0833],[0.3733,0.2693,0.0697],[0.5478,0.6073,0.0217],[0.6032,1.1046,-0.055],[0.1981,0.5742,0.0701],[0.856,0.0326,-0.0089],[0.248,0.2822,0.0757],[0.464,0.3874,0.0787],[0.1983,0.739,-0.0405],[0.1727,0.8195,-0.0734],[0.5454,0.5765,-0.072],[0.647,0.4065,-0.0609],[0.2295,0.3909,0.0941],[0.3934,0.2078,-0.0166],[0.3143,0.1946,-0.0365],[0.3854,0.3861,-0.0769],[0.5737,0.6701,0.039],[0.6038,0.9928,0.053],[0.7668,0.0304,0.0258],[0.1723,1.1231,0.065],[0.6463,0.1394,0.0385],[0.77,0.024,-0.0349],[0.2819,0.5924,-0.0085],[0.4124,0.5016,-0.0737],[0.2123,0.6259,-0.0288],[0.6839,-0.1203,-0.0652],[0.4668,0.2579,0.0713],[0.6303,0.2253,0.0538],[0.4447,0.4796,-0.0756],[0.1676,0.4361,0.0102],[0.7972,-0.1165,0.0053],[0.1362,1.0706,0.0615],[0.5938,1.0087,-0.0449],[0.1641,0.3584,0.0164],[0.1692,0.8289,0.0741],[0.1662,1.0256,0.0524],[0.4843,0.6049,-0.0453],[0.457,0.2032,0.0473],[0.1855,0.6988,0.0748],[0.5172,0.5832,0.0499],[0.6509,0.0892,0.0256],[0.6083,0.1527,0.0066],[0.203,0.4156,0.0796],[0.1821,0.4525,0.0441],[0.1895,0.5162,-0.0609],[0.672,0.0939,-0.0384],[0.7424,0.087,-0.0031],[0.6983,-0.1735,0.056],[0.3311,0.6219,-0.0039],[0.2904,0.6281,-0.0605],[0.1866,0.3434,0.0646],[0.3367,0.2761,-0.0696],[0.6655,0.1704,-0.0438],[0.5892,0.8085,-0.0716],[0.3593,0.628,-0.0116],[0.7976,-0.1053,-0.027],[0.4921,0.4537,0.0731],[0.7405,0.119,0.003],[0.6831,-0.1493,0.0656],[0.5515,0.1716,0.0428],[0.2779,0.6082,-0.0773],[0.2094,0.3884,-0.087],[0.5381,0.3769,0.0761],[0.7603,-0.1598,0.0286],[0.3085,0.2734,0.0712],[0.5548,0.6836,0.0625],[0.3939,0.2131,0.0372],[0.2338,0.5412,-0.0895],[0.1805,0.4867,-0.0331],[0.6227,0.5952,0.0142],[0.2291,0.4555,0.0931],[0.5735,1.1299,-0.0463],[0.5972,0.1607,-0.0082],[0.5586,0.4099,-0.08],[0.6012,0.1675,-0.0291],[0.6996,0.1935,-0.0356],[0.6822,-0.1108,0.0102],[0.5343,0.3285,0.0716],[0.5609,0.7285,-0.0552],[0.3271,0.2587,-0.0683],[0.5711,0.446,0.082],[0.69,-0.2008,0.0993],[0.559,0.2975,-0.0706],[0.4248,0.6193,0.045],[0.7367,-0.0599,-0.0417],[0.4115,0.2089,0.0283],[0.1804,0.4212,-0.055],[0.3175,0.5583,-0.0523],[0.6098,0.7318,-0.0441],[0.1674,0.7993,-0.0397],[0.4955,0.3479,-0.0725],[0.1776,0.8714,-0.0597],[0.6952,-0.1681,-0.0796],[0.6361,0.1476,0.0372],[0.6069,0.9054,-0.0516],[0.159,1.229,0.0605],[0.1549,0.9516,0.071],[0.7633,0.0359,-0.0082],[0.2527,0.5558,0.0293],[0.5041,0.4204,0.0732],[0.6775,0.4227,-0.0248],[0.5923,0.1821,-0.0408],[0.1675,0.4352,-0.0083],[0.155,1.1997,0.0507],[0.5169,0.2209,-0.058],[0.2721,0.1983,-0.0253],[0.5326,0.6038,-0.0376],[0.2596,0.4727,-0.0942],[0.604,0.2683,-0.0643],[0.8522,-0.0095,-0.022],[0.6816,0.4103,-0.0207],[0.1803,0.4515,-0.0394],[0.6879,-0.2015,-0.0805],[0.5921,0.7409,0.0731],[0.1972,0.2482,0.0376],[0.1647,1.0136,0.0675],[0.2773,0.2611,-0.0723],[0.7685,-0.153,0.0236],[0.313,0.4648,0.0844],[0.6971,-0.1846,-0.0651],[0.651,0.5214,0.0138],[0.7096,-0.1744,0.0709],[0.4334,0.5589,-0.0693],[0.3948,0.6311,-0.021],[0.7439,0.0845,-0.0],[0.6009,0.9439,0.0636],[0.7647,-0.0963,-0.043],[0.484,0.2629,-0.0697],[0.2505,0.4926,-0.0931],[0.2412,0.3748,-0.0952],[0.2019,0.6539,0.0796],[0.5821,0.9798,-0.0663],[0.197,0.5183,0.0103],[0.3218,0.5966,-0.0308],[0.2865,0.5398,-0.0885],[0.2308,0.3179,-0.0827],[0.4994,0.4905,0.0706],[0.5783,1.1112,0.0653],[0.3826,0.5714,-0.0599],[0.1445,1.1162,-0.0478],[0.4861,0.4516,-0.0739],[0.5896,1.0591,0.0455],[0.5615,0.4319,0.0816],[0.3214,0.3586,0.0814],[0.208,0.3154,-0.0779],[0.1666,1.1196,-0.0684],[0.2055,0.5152,0.0816],[0.5246,0.5978,0.0479],[0.3758,0.6078,0.045],[0.5766,0.3547,-0.0755],[0.319,0.2445,-0.0634],[0.3637,0.6145,-0.0383],[0.2159,0.6316,0.0302],[0.4019,0.2712,-0.0714],[0.8441,0.0327,-0.0104],[0.2137,0.4757,-0.0889],[0.6326,0.1491,0.0372],[0.7668,0.0357,-0.0143],[0.7024,-0.1576,-0.0482],[0.1824,0.5571,-0.0299],[0.2967,0.4227,0.0913],[0.6102,0.7222,-0.0438],[0.4331,0.6314,-0.0178],[0.1784,0.4595,0.0293],[0.5995,0.6081,0.0082],[0.226,0.6961,-0.0444],[0.5875,0.6512,0.0353],[0.4169,0.3751,-0.0787],[0.6203,0.1618,-0.0391],[0.5806,0.6257,0.0801],[0.5258,0.3588,0.0722],[0.1686,0.9637,0.0578],[0.1684,0.9674,-0.0633],[0.1539,0.7705,-0.0751],[0.8525,0.0286,0.014],[0.1753,0.8641,-0.0512],[0.3662,0.5638,0.0596],[0.5858,0.4082,0.0783],[0.4516,0.2561,0.071],[0.5974,1.0356,0.0469],[0.5757,0.7874,0.0407],[0.558,0.427,0.0814],[0.7073,0.1395,0.0336],[0.453,0.628,0.0177],[0.1684,0.7273,-0.0714],[0.6067,0.7506,0.04],[0.6958,-0.1908,-0.0694],[0.2885,0.584,0.0227],[0.1288,0.776,-0.0501],[0.6036,1.1083,-0.0546],[0.8614,-0.0593,0.002],[0.2617,0.469,-0.0944],[0.5736,0.8726,-0.0436],[0.3466,0.3346,-0.0726],[0.5901,0.8767,-0.0725],[0.6593,0.5023,-0.016],[0.5878,1.1788,0.0452],[0.5894,0.6954,0.076],[0.1618,1.086,-0.0498],[0.1851,0.7575,0.0748],[0.5522,0.5559,0.0831],[0.3487,0.4242,-0.0706],[0.5078,0.5471,0.0665],[0.7358,0.1501,-0.0065],[0.1326,0.7807,0.04],[0.5779,0.9718,0.0625],[0.5019,0.4755,0.0709],[0.8038,-0.0774,0.0271],[0.8071,-0.0615,0.0293],[0.5651,0.1731,0.0001],[0.5976,0.6191,0.0776],[0.5404,0.2964,-0.0704],[0.2634,0.2341,0.0616],[0.4725,0.3232,-0.074],[0.7939,-0.05,-0.0321],[0.1461,0.7895,0.0756],[0.5748,0.2043,0.0577],[0.6111,1.1603,0.0591],[0.1374,0.7872,-0.038],[0.1865,0.3498,-0.0651],[0.2238,0.4383,-0.0931],[0.6029,1.1578,0.046],[0.4441,0.6104,-0.0477],[0.3226,0.4025,0.0825],[0.8327,0.0108,-0.0231],[0.4809,0.6177,-0.0133],[0.5367,0.2155,-0.0619],[0.1432,1.0715,-0.0485],[0.6856,0.3776,-0.0273],[0.4977,0.2035,-0.0476],[0.6996,-0.1537,0.072],[0.688,0.1977,-0.0408],[0.5797,0.6839,0.038],[0.2314,0.57,-0.0875],[0.7086,0.2814,-0.0224],[0.8527,-0.0633,0.0044],[0.2334,0.4651,-0.0931],[0.4342,0.2651,-0.0726],[0.5928,1.0735,-0.0457],[0.3147,0.3678,-0.0849],[0.4798,0.5362,-0.0704],[0.3229,0.1909,0.0036],[0.4263,0.531,-0.0725],[0.6972,-0.1619,0.0758],[0.4385,0.2297,-0.0581],[0.196,0.7182,-0.0353],[0.2264,0.5468,0.0883],[0.449,0.1993,0.0252],[0.2094,0.6446,0.0811],[0.7005,0.1736,0.0359],[0.5613,0.6327,-0.0809],[0.2509,0.3323,-0.0883],[0.1491,0.9975,0.0688],[0.4857,0.3249,-0.0726],[0.2379,0.529,-0.0905],[0.1725,0.4582,-0.0125],[0.2499,0.5636,-0.0171],[0.717,0.2279,0.0231],[0.3015,0.4447,-0.0894],[0.5965,1.009,0.0647],[0.5697,0.8305,-0.0513],[0.1798,0.287,-0.0364],[0.6367,0.5443,0.0489],[0.1502,0.3191,-0.0101],[0.5446,0.6336,-0.0605],[0.3503,0.3526,0.0736],[0.6536,0.0671,0.0105],[0.5132,0.2923,0.068],[0.6119,0.6102,-0.0199],[0.592,0.6127,-0.0248],[0.2215,0.5552,-0.0873],[0.1917,0.437,0.0676],[0.5751,0.4951,0.0834],[0.6907,0.0287,-0.0343],[0.6815,-0.1685,0.0946],[0.235,0.5342,-0.0901],[0.5876,0.8991,-0.0706],[0.157,0.8517,0.0779],[0.5615,0.3396,0.074],[0.1312,1.1094,-0.0544],[0.6608,0.239,-0.051],[0.474,0.3847,-0.0772],[0.2232,0.5527,-0.0027],[0.1757,0.8009,-0.0736],[0.4906,0.5766,-0.0567],[0.165,0.401,-0.0013],[0.4377,0.5004,-0.0743],[0.5402,0.2813,-0.0692],[0.4081,0.6356,0.0131],[0.2104,0.4636,0.0855],[0.1888,0.5256,-0.0592],[0.2499,0.2068,0.0199],[0.2696,0.6161,0.0791],[0.3398,0.5317,0.0623],[0.3063,0.5826,0.0697],[0.7295,-0.1574,-0.0451],[0.6014,0.8746,-0.0424],[0.5014,0.6068,-0.0196],[0.7387,-0.0779,-0.0429],[0.1608,0.2922,-0.0158],[0.3009,0.3858,0.0903],[0.2118,0.6655,-0.0803],[0.3701,0.6287,-0.0134],[0.7577,-0.1303,-0.0479],[0.2215,0.2215,-0.0195],[0.3837,0.4063,-0.0756],[0.8364,0.0328,0.0031],[0.6769,0.0443,-0.0324],[0.6588,0.497,0.0247],[0.4147,0.2053,0.017],[0.8064,0.028,-0.0189],[0.6107,0.88,-0.0557],[0.5462,0.6046,-0.003],[0.732,0.0074,-0.0395],[0.3141,0.4812,-0.0835],[0.7259,0.1199,0.0232],[0.3614,0.6178,0.0296],[0.6032,0.8111,0.0435],[0.4026,0.5533,-0.0702],[0.2204,0.4634,-0.0925],[0.4151,0.2101,0.0365],[0.1626,0.806,-0.0775],[0.1991,0.6623,0.0296],[0.2717,0.4391,-0.0957],[0.6805,-0.1614,-0.0845],[0.5714,0.7824,-0.0433],[0.5683,0.1737,-0.0097],[0.2016,0.6697,-0.0788],[0.802,0.0341,0.0056],[0.2805,0.573,-0.032],[0.164,0.3798,-0.0219],[0.1693,0.9548,0.0629],[0.5644,0.3157,-0.0721],[0.3704,0.2624,-0.0679],[0.1607,0.7875,-0.0766],[0.5601,0.6183,-0.0384],[0.6606,0.0496,-0.0164],[0.8399,0.0327,-0.0112],[0.34,0.2621,0.0686],[0.6354,0.4533,-0.0692],[0.866,-0.0173,-0.0174],[0.5034,0.1864,-0.0209],[0.6117,0.605,0.0129],[0.4321,0.218,-0.0523],[0.7839,0.0265,0.0261],[0.6077,0.6857,-0.0699],[0.6064,0.4035,-0.0763],[0.241,0.6744,-0.0458],[0.6931,-0.1193,0.0786],[0.1499,0.9211,-0.043],[0.8722,-0.043,0.0103],[0.2648,0.611,0.0824],[0.5903,1.0331,-0.0669],[0.5187,0.5744,-0.0533],[0.4677,0.1971,0.0342],[0.7917,0.0342,-0.0108],[0.472,0.5297,-0.0714],[0.3258,0.5684,0.063],[0.4668,0.3796,0.0778],[0.5768,0.1741,-0.0387],[0.3788,0.4173,-0.0744],[0.4773,0.24,-0.0645],[0.5946,0.6146,-0.0304],[0.1592,1.1771,0.0708],[0.5703,0.8539,0.0508],[0.18,0.7243,0.0753],[0.202,0.5348,-0.0002],[0.6589,0.5004,-0.0203],[0.3839,0.5254,0.0691],[0.2696,0.2825,0.0802],[0.2551,0.3238,0.087],[0.4331,0.2067,-0.039],[0.4231,0.6204,-0.0446],[0.5914,0.9473,0.0434],[0.5736,0.8747,0.044],[0.4498,0.49,0.0751],[0.4254,0.4965,-0.0744],[0.5292,0.3109,0.0692],[0.7244,0.1015,0.0248],[0.5938,0.9484,0.0667],[0.1749,0.7532,0.0759],[0.4949,0.388,0.0747],[0.4481,0.2037,0.0409],[0.2283,0.5123,0.0907],[0.6389,0.11,-0.0195],[0.3774,0.5261,-0.0681],[0.1832,0.3486,-0.0619],[0.5362,0.3467,0.0734],[0.5764,0.9569,-0.0597],[0.7009,-0.0898,0.0471],[0.2301,0.426,0.0937],[0.3889,0.2046,-0.0043],[0.7105,0.0816,0.0329],[0.5784,0.6748,0.0769],[0.7988,-0.0281,-0.0314],[0.7561,-0.153,-0.0454],[0.705,-0.1527,-0.0492],[0.1369,0.9359,0.0539],[0.5922,0.1679,0.0179],[0.2712,0.3292,-0.0895],[0.5184,0.2643,0.0668],[0.1866,0.6936,-0.0749],[0.1326,1.1009,0.0566],[0.4181,0.6243,-0.0393],[0.2288,0.704,0.0485],[0.1495,0.7722,-0.0725],[0.6004,0.6123,0.0204],[0.3908,0.4937,0.0717],[0.624,0.5737,0.053],[0.2732,0.649,-0.0521],[0.5403,0.2208,0.065],[0.5392,0.1714,-0.0212],[0.2229,0.5371,0.0205],[0.2739,0.5988,-0.0809],[0.1706,0.8217,-0.074],[0.5568,0.1722,0.0231],[0.6072,0.7972,-0.0462],[0.4895,0.5358,-0.0696],[0.1748,0.4654,-0.0153],[0.6868,-0.136,0.0108],[0.8011,-0.1083,0.014],[0.7644,-0.127,0.0459],[0.5677,0.7499,-0.045],[0.5177,0.479,0.0701],[0.5261,0.2763,-0.0674],[0.6389,0.5238,-0.0525],[0.5421,0.5991,0.0654],[0.3636,0.3374,-0.0735],[0.4333,0.624,0.0365],[0.2848,0.5971,-0.0469],[0.6809,0.097,0.0389],[0.1843,0.531,-0.0427],[0.1836,0.571,-0.0322],[0.2417,0.6291,-0.0853],[0.6104,1.2026,-0.0663],[0.6882,-0.2231,0.1091],[0.1842,0.6147,-0.0428],[0.6201,1.228,-0.0448],[0.7466,0.0289,-0.0228],[0.2537,0.6579,0.0733],[0.5524,0.6365,0.0769],[0.1666,0.9035,0.0476],[0.5752,0.538,-0.0837],[0.2778,0.472,0.0951],[0.1737,0.6813,0.054],[0.6206,0.5959,-0.0495],[0.1816,0.8153,-0.049],[0.5976,1.1604,-0.0675],[0.6232,0.5863,0.0415],[0.504,0.5449,0.0681],[0.2765,0.2665,0.0741],[0.1625,1.0797,0.0496],[0.4082,0.5337,-0.072],[0.1364,1.0701,0.0511],[0.6093,0.7015,0.0402],[0.5051,0.2114,0.0515],[0.1315,0.7729,-0.0594],[0.4942,0.5633,-0.062],[0.3678,0.4269,-0.0727],[0.1713,0.3092,-0.0394],[0.5512,0.6238,-0.0798],[0.1816,0.5094,0.021],[0.8027,-0.0268,0.0305],[0.6963,-0.0344,0.0321],[0.6741,0.3839,0.0406],[0.1733,0.7346,-0.075],[0.1709,1.0124,0.0569],[0.592,0.7336,-0.0733],[0.1438,0.9994,-0.0657],[0.1716,0.9215,0.0641],[0.7018,-0.0372,-0.0336],[0.4267,0.3941,-0.0794],[0.1856,0.7989,-0.0702],[0.6385,0.3748,0.0633],[0.136,0.88,0.0443],[0.5999,1.103,0.0508],[0.3953,0.6277,-0.0298],[0.5726,0.7434,0.0725],[0.699,-0.1557,-0.0206],[0.342,0.2268,-0.0516],[0.1985,0.737,-0.04],[0.6437,0.426,0.063],[0.153,0.3686,-0.0121],[0.6471,0.5344,0.0064],[0.685,-0.1907,-0.0771],[0.2589,0.6193,0.0828],[0.5946,0.1782,0.0393],[0.5028,0.384,-0.0734],[0.3196,0.6075,0.0151],[0.3776,0.5448,0.0672],[0.6758,0.0305,-0.0293],[0.4201,0.5726,-0.0629],[0.1868,1.217,-0.0684],[0.598,0.4399,-0.0798],[0.1317,0.8458,0.0494],[0.5531,0.4646,-0.0826],[0.5974,1.1582,-0.0448],[0.6552,0.32,-0.0533],[0.7644,-0.1591,-0.0126],[0.5826,1.0767,-0.0463],[0.1697,1.1691,-0.0481],[0.4182,0.6337,-0.0156],[0.77,-0.0649,-0.0397],[0.3328,0.4785,0.0707],[0.6946,-0.2142,0.0959],[0.3091,0.4443,-0.0866],[0.1651,1.205,0.0482],[0.1694,1.229,-0.0508],[0.3026,0.5147,0.0871],[0.6569,0.0544,-0.0097],[0.6116,0.6016,-0.0717],[0.6474,0.2561,0.055],[0.1772,0.4497,-0.0311],[0.8295,0.0273,0.0193],[0.6067,0.9121,-0.0533],[0.1537,1.0043,0.0481],[0.8651,0.0091,-0.0113],[0.2123,0.6727,0.08],[0.6084,1.229,0.069],[0.607,0.8683,0.044],[0.2833,0.3027,-0.0826],[0.5706,0.6964,0.0404],[0.681,-0.2084,0.1206],[0.283,0.4924,-0.0948],[0.7085,-0.1736,-0.0679],[0.1803,0.6495,-0.0582],[0.735,0.1622,0.006],[0.5681,0.4656,0.0827],[0.6192,0.6166,0.0494],[0.3431,0.6175,-0.0192],[0.2255,0.2895,-0.0739],[0.6102,0.2484,-0.0609],[0.5909,0.8464,-0.0714],[0.1514,1.109,-0.071],[0.8147,-0.025,-0.0279],[0.2694,0.3847,-0.097],[0.6201,0.5963,0.048],[0.3402,0.5557,0.0591],[0.3484,0.2009,-0.0072],[0.1699,1.0922,-0.0669],[0.3704,0.6221,0.0248],[0.5609,0.6906,0.0749],[0.2527,0.2514,-0.0665],[0.6632,0.4894,0.0146],[0.5654,0.7516,0.0499],[0.6774,0.1016,-0.0392],[0.284,0.6133,-0.074],[0.3819,0.6089,0.0459],[0.1374,1.0489,-0.0617],[0.648,0.2253,0.0511],[0.1684,0.9771,-0.0594],[0.2278,0.2361,0.049],[0.4429,0.517,-0.0735],[0.5867,0.7293,0.0752],[0.3784,0.3615,0.0759],[0.7132,-0.0338,-0.0411],[0.5846,0.6895,-0.0371],[0.5829,0.6739,0.0371],[0.6055,0.3085,0.068],[0.646,0.2522,-0.0548],[0.1997,0.4472,-0.0752],[0.7418,-0.1276,-0.0473],[0.2448,0.2066,0.0099],[0.5972,0.8822,0.0689],[0.7044,0.2897,-0.0274],[0.4612,0.428,0.0777],[0.7503,-0.1469,-0.0462],[0.6429,0.1149,-0.0331],[0.4221,0.2843,-0.0733],[0.554,0.6553,0.0724],[0.7784,0.0054,-0.0355],[0.169,1.166,0.0698],[0.6674,0.4629,-0.0276],[0.6933,-0.1264,0.0259],[0.222,0.6213,0.0305],[0.2789,0.5795,-0.0217],[0.1808,0.486,0.0091],[0.208,0.509,0.0839],[0.4069,0.5812,-0.06],[0.6003,0.2846,0.0665],[0.5849,0.9715,0.0444],[0.7412,-0.175,-0.0115],[0.6074,0.5887,-0.0743],[0.6952,-0.0774,0.0308],[0.2941,0.4434,0.0919],[0.6629,0.0617,-0.0298],[0.3969,0.5658,0.0646],[0.5226,0.181,0.0312],[0.7114,0.006,-0.036],[0.1385,1.1212,0.0649],[0.539,0.1664,-0.04],[0.4485,0.4899,-0.0751],[0.326,0.5643,-0.0499],[0.223,0.2297,0.0422],[0.4801,0.194,0.0317],[0.6281,0.4564,0.0725],[0.5839,0.6294,-0.0352],[0.1696,0.9529,-0.0539],[0.317,0.5633,0.048],[0.25,0.5025,0.0926],[0.5737,0.9623,-0.0539],[0.5876,0.9374,-0.0684],[0.1983,0.4415,0.074],[0.2079,0.7555,0.0646],[0.7323,-0.118,0.0455],[0.2263,0.2713,-0.0673],[0.2717,0.2043,-0.041],[0.6038,1.1124,-0.0547],[0.5777,1.0014,-0.0612],[0.1657,0.3423,-0.0067],[0.2294,0.5085,0.091],[0.4502,0.6269,0.0238],[0.1865,0.3684,-0.0663],[0.7756,-0.1416,0.0365],[0.5632,0.6953,0.0747],[0.255,0.4449,0.0947],[0.7214,0.1191,0.0266],[0.7562,-0.1676,-0.0009],[0.2954,0.5933,-0.0165],[0.8299,0.0326,0.0133],[0.4204,0.2345,0.058],[0.2575,0.5855,0.0342],[0.1884,0.4866,0.0615],[0.7154,-0.0639,0.0412],[0.5326,0.5091,0.076],[0.608,0.7742,0.0452],[0.4841,0.6153,-0.0175],[0.56,0.4983,0.0833],[0.188,0.4947,0.0601],[0.5737,0.1726,-0.0379],[0.2724,0.6253,0.0471],[0.3217,0.5627,0.0682],[0.5639,0.6429,0.0799],[0.6022,0.9461,0.0475],[0.2663,0.5795,0.013],[0.5127,0.6041,-0.012],[0.1606,1.0217,-0.0699],[0.2867,0.5872,0.0177],[0.1601,1.1871,0.0712],[0.1467,0.984,0.0461],[0.6765,0.0127,0.0271],[0.23,0.4381,0.0935],[0.582,0.8996,-0.0692],[0.269,0.6401,-0.0725],[0.3495,0.2284,0.051],[0.6104,0.4428,0.0776],[0.5099,0.187,0.0328],[0.1826,0.7748,0.0733],[0.5278,0.5397,-0.0748],[0.5095,0.3554,0.0712],[0.6469,0.1188,0.0349],[0.7084,0.2343,-0.029],[0.6174,0.6462,0.0503],[0.3275,0.5635,0.0572],[0.6094,0.3954,-0.0745],[0.6052,0.6583,-0.0356],[0.5566,0.6056,0.0165],[0.7293,0.0988,-0.0212],[0.7163,-0.1058,-0.0451],[0.487,0.6136,0.0186],[0.725,0.2427,-0.003],[0.6707,0.4329,0.0369],[0.4957,0.6091,-0.0205],[0.6008,0.4552,-0.0807],[0.4877,0.19,0.0219],[0.4668,0.5866,0.0561],[0.4192,0.5254,-0.0727],[0.1581,0.825,-0.0773],[0.3684,0.6245,0.0201],[0.1708,1.0202,-0.0617],[0.5314,0.568,-0.0673],[0.1812,0.4678,-0.0377],[0.5737,0.8704,-0.0633],[0.144,0.8104,-0.0742],[0.3249,0.192,0.0064],[0.7162,-0.1097,-0.045],[0.1992,0.4893,0.0751],[0.3538,0.6044,-0.0419],[0.1636,1.229,-0.0598],[0.7571,-0.0138,0.0415],[0.1982,0.2432,-0.0026],[0.5752,0.2951,0.0719],[0.2587,0.355,-0.0934],[0.5099,0.5313,-0.0681],[0.413,0.4102,0.078],[0.5866,1.0596,0.0658],[0.5436,0.2778,0.0697],[0.186,0.8256,0.0525],[0.6679,0.4758,0.0106],[0.629,0.2704,0.0595],[0.1642,0.3829,0.0011],[0.188,0.5818,-0.0508],[0.6681,0.2398,-0.048],[0.6746,0.3785,-0.0405],[0.8589,-0.0212,-0.0215],[0.5381,0.2946,0.0698],[0.7227,-0.1387,-0.0442],[0.407,0.2809,-0.0723],[0.169,0.4354,-0.0151],[0.764,0.0358,-0.0005],[0.6119,0.4498,-0.0776],[0.2733,0.653,-0.0532],[0.1484,1.178,0.0626],[0.5735,1.1365,-0.0446],[0.3754,0.63,0.0126],[0.196,0.5206,0.0036],[0.8712,-0.0573,-0.0015],[0.4113,0.5173,-0.0729],[0.1679,0.3297,-0.0302],[0.1871,0.3133,-0.0592],[0.1731,0.271,-0.0016],[0.5957,1.1836,0.0436],[0.5542,0.6254,-0.0432],[0.3746,0.2968,0.0715],[0.577,0.8024,0.0407],[0.4102,0.2733,-0.0719],[0.2453,0.2125,0.0334],[0.2345,0.212,-0.0081],[0.229,0.6533,-0.0827],[0.1803,0.3684,0.0601],[0.4424,0.2717,-0.0735],[0.4964,0.5301,0.0692],[0.1355,0.9178,-0.0501],[0.3244,0.1926,0.0131],[0.4313,0.2022,-0.0205],[0.6793,-0.1876,0.1029],[0.565,0.7259,0.0722],[0.6032,0.1765,-0.0413],[0.6683,0.2364,-0.048],[0.7932,-0.12,0.0277],[0.54,0.6032,-0.0617],[0.1591,1.2261,-0.07],[0.5997,1.0282,0.0626],[0.593,0.6893,0.0752],[0.407,0.6272,0.0345],[0.2959,0.3704,-0.092],[0.6018,0.1553,0.0033],[0.6018,0.8842,0.0667],[0.6924,-0.172,0.0855],[0.6919,-0.1145,-0.026],[0.6205,0.6054,0.0516],[0.5291,0.4358,-0.076],[0.5568,0.607,-0.0248],[0.8418,-0.0685,-0.0076],[0.1522,0.7729,-0.0348],[0.536,0.6053,-0.0144],[0.1684,1.0148,-0.0655],[0.7376,-0.047,-0.0409],[0.2841,0.1986,0.0322],[0.2729,0.6363,0.0715],[0.6522,0.0567,-0.001],[0.1514,1.1787,-0.0489],[0.6005,0.6205,0.0762],[0.7161,-0.1743,0.023],[0.5624,0.1726,-0.0116],[0.7215,0.0709,-0.0275],[0.5963,1.0396,-0.0462],[0.4731,0.2239,0.0571],[0.3885,0.6301,-0.0187],[0.602,1.1358,-0.0642],[0.1347,1.0952,-0.0516],[0.2312,0.3239,-0.0841],[0.8565,0.0314,0.0036],[0.4693,0.621,-0.0163],[0.5592,0.4524,-0.0826],[0.1707,0.4312,0.0217],[0.8724,-0.0196,0.0068],[0.5519,0.2738,0.0691],[0.6441,0.3285,-0.0588],[0.7142,-0.1643,-0.0301],[0.6161,0.608,0.0642],[0.5873,0.2615,0.0657],[0.4183,0.2012,-0.0044],[0.4736,0.2838,0.0719],[0.5719,0.9045,0.0534],[0.495,0.4864,-0.0712],[0.2179,0.529,-0.0885],[0.1933,0.6959,0.076],[0.6939,-0.2055,-0.0913],[0.5602,0.4029,0.0793],[0.5543,0.6354,0.0805],[0.667,0.4516,-0.037],[0.1849,0.5073,-0.0475],[0.5274,0.3151,-0.0692],[0.6131,0.4071,0.0738],[0.813,-0.0926,0.0187],[0.5042,0.2186,0.055],[0.2619,0.5741,0.0165],[0.5568,0.5365,-0.0834],[0.1598,0.2921,-0.0129],[0.3949,0.4868,0.0727],[0.7381,0.0179,-0.0385],[0.608,0.6764,-0.0366],[0.6653,0.0161,0.0108],[0.179,0.6483,0.0545],[0.3955,0.2597,0.0669],[0.6314,0.5724,0.0009],[0.1292,0.7753,0.0416],[0.744,-0.175,-0.0024],[0.1861,0.347,-0.0645],[0.1737,1.0968,0.06],[0.4979,0.6082,-0.0202],[0.3551,0.2045,0.0101],[0.2082,0.2299,0.0282],[0.5882,0.6672,-0.0778],[0.1654,1.1937,-0.047],[0.5999,1.0959,-0.051],[0.1657,1.229,-0.0555],[0.1943,1.2247,-0.0529],[0.7405,-0.1764,0.0062],[0.2293,0.6884,0.0441],[0.7249,0.1601,-0.0218],[0.2294,0.2562,0.0631],[0.6822,-0.1627,0.0979],[0.5234,0.5973,0.0435],[0.145,0.7434,-0.0436],[0.4168,0.2509,-0.0651],[0.7418,-0.0362,0.041],[0.1778,0.4869,-0.023],[0.3172,0.1891,0.0062],[0.2017,0.7042,-0.0344],[0.1408,0.778,-0.0369],[0.3057,0.1894,-0.0066],[0.685,-0.1319,-0.0083],[0.256,0.2065,0.0302],[0.5408,0.1696,0.029],[0.5826,0.8411,0.0405],[0.624,0.5189,-0.0669],[0.5715,0.7852,-0.0437],[0.2594,0.6012,0.0374],[0.4522,0.2572,-0.0715],[0.176,0.3689,-0.0535],[0.6828,0.0881,-0.0383],[0.474,0.6187,0.018],[0.4482,0.5734,0.0637],[0.2077,0.7662,-0.055],[0.1731,0.7781,-0.0392],[0.5838,0.9366,0.0675],[0.2199,0.7015,0.0727],[0.4132,0.2344,0.0572],[0.6326,0.3578,-0.0649],[0.156,0.7935,-0.0766],[0.1775,0.8786,-0.0573],[0.6329,0.4633,0.0713],[0.6052,1.1282,0.0556],[0.5368,0.5903,0.0637],[0.4832,0.2423,0.0656],[0.1816,0.5155,-0.0217],[0.4779,0.2381,-0.0636],[0.7082,-0.1544,-0.0316],[0.6084,0.8956,-0.0524],[0.7121,-0.1534,0.0376],[0.1629,1.0768,0.0496],[0.1458,1.1447,0.0636],[0.5994,1.1871,0.0678],[0.2784,0.4351,0.0961],[0.672,0.4417,-0.0292],[0.1672,0.395,-0.0309],[0.748,-0.1648,0.0323],[0.1409,0.9864,0.0623],[0.753,-0.1667,0.0162],[0.1878,0.4879,-0.0601],[0.7041,-0.1819,0.0706],[0.2529,0.6283,0.0396],[0.3315,0.1967,0.0249],[0.6673,0.4786,0.0097],[0.1814,0.4912,-0.0027],[0.7791,-0.0375,-0.0366],[0.598,0.3813,0.0758],[0.4408,0.1948,-0.0008],[0.2159,0.6392,0.0821],[0.6083,0.7635,0.0616],[0.5793,1.1006,0.0465],[0.5695,0.6817,-0.0402],[0.6299,1.2258,-0.0463],[0.244,0.634,-0.0839],[0.5585,0.1728,-0.0151],[0.1818,0.6301,0.0515],[0.5814,0.8017,-0.04],[0.7113,-0.1692,-0.0671],[0.6353,0.3887,0.0648],[0.5881,0.8214,0.0395],[0.6164,0.2824,0.0637],[0.3009,0.2962,-0.0783],[0.328,0.1956,-0.0266],[0.6056,0.5435,-0.0779],[0.2823,0.2908,-0.0801],[0.3006,0.1958,0.0316],[0.681,-0.2201,-0.1101],[0.1935,0.4403,0.0692],[0.3618,0.5216,-0.0664],[0.3788,0.6264,0.0204],[0.8738,-0.0418,-0.0053],[0.1899,0.3524,0.0684],[0.1781,0.469,0.0262],[0.2856,0.6041,0.076],[0.6371,0.5479,-0.0329],[0.5817,0.7252,-0.0384],[0.3409,0.2548,-0.0653],[0.5812,0.6277,0.08],[0.689,-0.1368,-0.1025],[0.5768,0.3187,0.0731],[0.685,0.1841,-0.0427],[0.1822,0.3058,0.0526],[0.3298,0.2915,-0.0719],[0.5069,0.514,-0.069],[0.1318,0.7711,0.0493],[0.4615,0.3235,-0.0753],[0.6008,0.3347,0.0713],[0.1992,0.7573,-0.0458],[0.6119,0.1742,-0.0426],[0.1587,0.717,-0.053],[0.7938,0.0342,0.0019],[0.2233,0.6955,0.0732],[0.6724,-0.0054,-0.0173],[0.5944,0.6073,-0.0797],[0.5706,1.1423,-0.0578],[0.6014,1.1031,0.0521],[0.3375,0.2767,-0.0695],[0.3179,0.5907,0.0585],[0.465,0.4802,-0.0744],[0.805,-0.0557,0.0298],[0.8209,-0.0796,-0.0204],[0.5917,0.828,0.0701],[0.2552,0.6016,0.0881],[0.6401,0.3274,-0.0606],[0.1691,0.2891,0.0189],[0.5916,1.1567,-0.0662],[0.5973,1.0708,0.063],[0.4029,0.441,-0.0761],[0.5999,0.342,0.0722],[0.5945,0.887,0.0697],[0.3241,0.5038,0.0774],[0.1718,0.454,-0.0131],[0.6925,-0.1188,0.0798],[0.2337,0.2289,-0.0458],[0.3235,0.397,-0.0823],[0.2992,0.2723,-0.0721],[0.1679,0.3211,0.024],[0.5322,0.1791,0.0078],[0.7009,-0.1166,-0.0643],[0.5768,0.9256,-0.0618],[0.1601,1.0444,-0.049],[0.411,0.2189,0.05],[0.2168,0.2471,-0.053],[0.646,0.5229,-0.0301],[0.3903,0.3712,0.0773],[0.7183,0.1494,-0.028],[0.3173,0.5866,0.0344],[0.246,0.2788,-0.074],[0.7086,-0.0243,-0.0376],[0.4578,0.618,-0.0393],[0.7333,-0.0379,0.0408],[0.6391,0.1127,-0.0233],[0.7357,-0.1801,0.0027],[0.4362,0.2026,-0.0264],[0.3668,0.2128,0.0344],[0.3691,0.2113,-0.0288],[0.5958,0.333,0.0716],[0.599,1.2119,0.0451],[0.5819,0.7669,0.0725],[0.5388,0.2761,-0.0685],[0.1678,0.4274,0.0158],[0.6097,0.7588,0.0584],[0.1717,0.9195,-0.0616],[0.4437,0.204,-0.0382],[0.1974,0.247,0.0156],[0.2183,0.5656,-0.0863],[0.1371,1.0392,-0.06],[0.6197,0.4359,0.0739],[0.7747,-0.0008,0.0374],[0.1626,1.0645,0.0494],[0.3587,0.2348,-0.0532],[0.6309,0.5165,0.0622],[0.4829,0.2378,0.0635],[0.7445,-0.0283,-0.0414],[0.6798,-0.1931,-0.1084],[0.1438,0.746,-0.0438],[0.5681,1.1392,0.0578],[0.5546,0.2258,-0.0669],[0.5649,0.6529,-0.0788],[0.5498,0.6463,-0.0667],[0.1672,0.76,0.0755],[0.2824,0.583,0.0811],[0.4165,0.2086,0.0317],[0.3922,0.3073,-0.0732],[0.3297,0.3594,0.079],[0.3879,0.218,0.047],[0.4246,0.4032,-0.0789],[0.5857,0.9075,0.0695],[0.4296,0.5427,0.0719],[0.2956,0.2173,-0.0539],[0.1515,1.0532,-0.0487],[0.2233,0.583,-0.027]];
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
    let audio, volume = 0.4, master, frame = 0, previous = 0, launchIn = 0, fireworksElapsed = 0;
    let width = innerWidth, height = innerHeight, rockets = [], sparks = [], groundEffects = [], drone = null;
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
    level.type = "range"; level.min = "0"; level.max = "100"; level.value = "40";
    level.setAttribute("aria-label", "Fireworks volume");
    on(level, "input", () => { volume = Number(level.value) / 100; syncAudio(); });
    controls.append(level);
    const styles = ["Peony", "Ring", "Palm", "Willow", "Crackle", "Roman candle bank", "Fountain", "Fan jets", "Mine"];
    let pendingKind = null, status;
    if (preview) {
      const clock = document.createElement("input"); clock.type = "datetime-local";
      clock.value = new Date(simulated).toISOString().slice(0, 19); clock.setAttribute("aria-label", "Simulated UTC time");
      on(clock, "change", () => {
        const next = Date.parse(clock.value + "Z");
        if (Number.isFinite(next)) { simulated = next; rockets = []; sparks = []; groundEffects = []; drone = null; fireworksElapsed = 0; pendingKind = null; refresh(); }
      }); controls.append(clock);
      const rate = document.createElement("input"); rate.type = "number"; rate.min = "0"; rate.max = "3600";
      rate.value = String(speed); rate.setAttribute("aria-label", "Clock speed");
      on(rate, "change", () => { const next = Number(rate.value); if (Number.isFinite(next) && next >= 0 && next <= 3600) speed = next; });
      controls.append(rate);
      button("Burst", "Launch a test firework", () => { if (active()) launch(); draw(); });
      button("Step", "Advance fireworks one frame", () => { advance(1 / 60); draw(); });
      button("Reset", "Reset fireworks", () => { seed = 42; fireworksElapsed = 0; pendingKind = null; rockets = []; sparks = []; groundEffects = []; drone = null; launchIn = 0; draw(); });
      status = document.createElement("output"); controls.append(status);
    }
    function syncAudio() {
      if (!master) return;
      const audible = sound && !paused && !hidden && !document.hidden && !printing && active();
      master.gain.setTargetAtTime(audible ? volume * 0.55 : 0, audio.currentTime, 0.02);
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
    function tone(startFrequency, endFrequency, duration, strength, delay = 0) {
      if (!sound || !audio || audio.state !== "running" || document.hidden ||
          paused || hidden || !active()) return;
      const oscillator = audio.createOscillator(), gain = audio.createGain();
      const when = audio.currentTime + delay;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(startFrequency, when);
      oscillator.frequency.exponentialRampToValueAtTime(endFrequency, when + duration);
      gain.gain.setValueAtTime(0.001, when);
      gain.gain.exponentialRampToValueAtTime(strength, when + Math.min(0.05, duration / 4));
      gain.gain.exponentialRampToValueAtTime(0.001, when + duration);
      oscillator.connect(gain); gain.connect(master);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
      oscillator.start(when); oscillator.stop(when + duration);
    }
    function launch() {
      if ((config.drone !== false && fireworksElapsed >= 120) || drone || groundEffects.length || sparks.some(p => p.ground) || rockets.length >= 5 || sparks.length > 1000) return;
      // Keep a selected ground sequence queued while the aerial display clears.
      // Rerolling here allowed new aerial launches to starve ground effects.
      if (!pendingKind) pendingKind = styles[Math.floor(random() * styles.length)];
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
      noise(0.55, 1900);
      // A sustained rising whistle follows selected rockets towards their apex.
      if (["Ring", "Palm", "Crackle"].includes(kind) || Math.random() < 0.3) {
        const ascent = Math.max(0.2, (height + 5 - target) / 250);
        tone(650 + Math.random() * 250, 1900 + Math.random() * 500, ascent, 0.30);
      }
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
      // Every aerial burst has an audible report, with a deeper rumble for
      // the larger shells and brighter snaps for rings and crackling effects.
      const heavy = ["Peony", "Palm", "Willow"].includes(rocket.kind);
      noise(heavy ? 1.4 : 0.8, heavy ? 300 : 1100, 0.12);
      tone(heavy ? 95 : 145, heavy ? 28 : 55, heavy ? 1.25 : 0.65,
        heavy ? 0.9 : 0.55, 0.12);
      if (heavy) noise(1.6, 130, 0.18);
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
    function volumeTargets(scene) {
      if (scene === "Deer") return droneDeerSurface.map(([x,y,z]) => ({x,y,z}));
      const points = [];
      function ellipsoid(cx, cy, cz, rx, ry, rz, count = 160) {
        for (let i=0;i<count;i++) {
          const h=1-2*(i+0.5)/count, r=Math.sqrt(1-h*h), a=i*Math.PI*(3-Math.sqrt(5));
          points.push({x:cx+rx*r*Math.cos(a), y:cy+ry*h, z:cz+rz*r*Math.sin(a)});
        }
      }
      function wing(side, butterfly) {
        for (let i=0;i<280;i++) {
          const u=(i+0.5)/280, a=i*Math.PI*(3-Math.sqrt(5));
          const length=butterfly ? 0.30*Math.sin(Math.PI*u) : 0.11+0.18*Math.sin(Math.PI*u);
          const x=0.5+side*(0.04+u*0.36);
          points.push({x,y:0.48+Math.cos(a)*length,
            z:Math.sin(a)*0.035*Math.sin(Math.PI*u)});
        }
      }
      if (scene === "Bird" || scene === "Butterfly") {
        ellipsoid(0.5,0.55,0,0.055,0.25,0.06,220);
        ellipsoid(0.5,0.30,0,0.06,0.07,0.06,100);
        wing(-1,scene==="Butterfly"); wing(1,scene==="Butterfly");
        if(scene==="Bird") ellipsoid(0.5,0.20,0,0.018,0.08,0.025,55);
      } else if (scene === "Dolphin") {
        for(let i=0;i<650;i++) {
          const u=(i+0.5)/650, a=i*Math.PI*(3-Math.sqrt(5));
          const r=0.11*Math.pow(Math.sin(Math.PI*u),0.8);
          points.push({x:0.14+u*0.65,y:0.48+Math.cos(a)*r*1.6+0.06*Math.sin(u*Math.PI),
            z:Math.sin(a)*r});
        }
        ellipsoid(0.82,0.48,0,0.10,0.035,0.035,90);
        ellipsoid(0.14,0.49,0,0.06,0.035,0.19,120);
        ellipsoid(0.48,0.35,0,0.06,0.16,0.025,110);
        ellipsoid(0.56,0.62,0.10,0.08,0.10,0.08,80);
        ellipsoid(0.56,0.62,-0.10,0.08,0.10,0.08,80);
      } else if (scene === "Globe") {
        ellipsoid(0.5,0.5,0,0.24,0.48,0.24,1000);
      } else if (scene === "Heart") {
        for(let i=0;i<1000;i++) {
          const h=1-2*(i+0.5)/1000, r=Math.sqrt(1-h*h), a=i*Math.PI*(3-Math.sqrt(5));
          const x=16*Math.pow(Math.sin(a),3);
          const y=13*Math.cos(a)-5*Math.cos(2*a)-2*Math.cos(3*a)-Math.cos(4*a);
          points.push({x:0.5+x*r*0.017,y:0.48-y*r*0.028,z:h*0.13});
        }
      } else if (scene === "Star") {
        for(let i=0;i<900;i++) {
          const h=1-2*(i+0.5)/900, a=i*Math.PI*(3-Math.sqrt(5));
          const section=1-Math.abs(h), tip=(Math.cos(a*5)+1)/2;
          const radius=(0.15+0.17*tip)*section;
          points.push({x:0.5+Math.cos(a)*radius,y:0.5+Math.sin(a)*radius*2,z:h*0.13});
        }
      } else if (scene === "Tree") {
        for(let tier=0;tier<3;tier++) for(let i=0;i<260;i++) {
          const u=(i+0.5)/260,a=i*Math.PI*(3-Math.sqrt(5)),r=u*(0.13+tier*0.045);
          points.push({x:0.5+Math.cos(a)*r,y:0.08+tier*0.19+u*0.37,z:Math.sin(a)*r});
        }
        ellipsoid(0.5,0.86,0,0.035,0.1,0.035,90);
      } else if (scene === "Flower") {
        ellipsoid(0.5,0.5,0,0.065,0.13,0.10,150);
        for(let petal=0;petal<8;petal++) {
          const a=petal*Math.PI/4;
          ellipsoid(0.5+Math.cos(a)*0.17,0.5+Math.sin(a)*0.34,0,
            0.10,0.15,0.065,100);
        }
      }
      return points;
    }
    function droneTargets(scene) {
      if (scene !== "Happy New Year") return volumeTargets(scene);
      const mask = document.createElement("canvas"); mask.width = 360; mask.height = 180;
      const pen = mask.getContext("2d");
      pen.strokeStyle = "white"; pen.fillStyle = "white"; pen.lineWidth = 3;
      pen.lineCap = "round"; pen.lineJoin = "round";
      pen.textAlign = "center"; pen.font = "bold 45px sans-serif";
      pen.fillText("HAPPY", 180, 68); pen.fillText("NEW YEAR", 180, 125);
      const pixels = pen.getImageData(0,0,360,180).data, points = [];
      for (let y=0;y<180;y+=4) for (let x=0;x<360;x+=4) {
        if (pixels[(y*360+x)*4+3]>80) {
          const depth = scene === "Happy New Year" ? 0.035 : 0.10;
          for (const z of [-depth, 0, depth]) points.push({x:x/360,y:y/180,z});
        }
      }
      return points;
    }
    function startDrones() {
      drone = {elapsed:0, scene:-1, targets:[], points:[], name:""};
    }
    function advanceDrones(dt) {
      drone.elapsed += dt;
      if (drone.elapsed >= 120) { drone = null; fireworksElapsed = 0; launchIn = 0; return; }
      const scene = Math.floor(drone.elapsed / 12);
      const names = ["Happy New Year", "Bird", "Deer", "Dolphin", "Butterfly", "Heart", "Star", "Globe", "Tree", "Flower"];
      if (scene !== drone.scene) {
        drone.scene = scene; drone.name = names[scene]; drone.targets = droneTargets(drone.name);
        while (drone.points.length < drone.targets.length) drone.points.push({x:random(),y:1.1,z:0});
      }
      const ease = 1 - Math.exp(-dt * 1.7);
      drone.points.forEach((p,i) => {
        const target = drone.targets[i] || {x:0.5,y:1.15,z:0};
        p.x += (target.x-p.x)*ease; p.y += (target.y-p.y)*ease; p.z += (target.z-p.z)*ease;
      });
    }
    function drawDrones() {
      const span = Math.min(width * 0.80, 800, height * 1.25), tall = span / 2;
      const time = drone.elapsed;
      const yaw = drone.name === "Globe" ? time * 0.35 : Math.sin(time * 0.30) * 1.15;
      const pitch = Math.sin(time * 0.32) * 0.14;
      const projected = drone.points.map((point, i) => {
        let x = point.x - 0.5, y = (point.y - 0.5) / 2, z = point.z;
        if (drone.name === "Bird" || drone.name === "Butterfly") {
          const wing = Math.min(1, Math.abs(x) * 3);
          z += Math.sin(time * (drone.name === "Bird" ? 3 : 5)) * wing * 0.14;
          y += Math.cos(time * 3) * wing * 0.025;
        } else if (drone.name === "Dolphin") {
          y += Math.sin(time * 2.2 + x * 7) * 0.045;
          z += Math.cos(time * 2.2 + x * 5) * 0.035;
        } else if (drone.name === "Deer") {
          // A gentle diagonal-pair trot. Rotate each leg around its own
          // shoulder/hip, then flex the lower leg only during the swing.
          const stride = time * 3.2;
          y -= (1 - Math.cos(stride * 2)) * 0.004;
          if (point.y > 0.59) {
            const front = point.x > 0.4, farSide = point.z < 0;
            const phase = stride + (front !== farSide ? Math.PI : 0);
            const hipX = (front ? 0.59 : 0.20) - 0.5;
            const hipY = (0.59 - 0.5) / 2;
            const kneeX = (front ? 0.59 : 0.16) - 0.5;
            const kneeY = (0.86 - 0.5) / 2;
            const swing = Math.sin(phase) * 0.28;
            const flex = Math.max(0, Math.cos(phase)) * (front ? -0.55 : 0.55);
            let legX = point.x - 0.5, legY = (point.y - 0.5) / 2;
            if (point.y > 0.86) {
              const dx = legX - kneeX, dy = legY - kneeY;
              legX = kneeX + dx * Math.cos(flex) - dy * Math.sin(flex);
              legY = kneeY + dx * Math.sin(flex) + dy * Math.cos(flex);
            }
            const dx = legX - hipX, dy = legY - hipY;
            const blend = Math.min(1, (point.y - 0.59) / 0.09);
            x += (hipX + dx * Math.cos(swing) - dy * Math.sin(swing) - x) * blend;
            y += (hipY + dx * Math.sin(swing) + dy * Math.cos(swing) -
              (point.y - 0.5) / 2) * blend;
          }
        } else if (drone.name === "Heart") {
          const pulse = 1 + Math.sin(time * 3) * 0.055;
          x *= pulse; y *= pulse; z *= pulse;
        } else if (drone.name === "Star" || drone.name === "Flower") {
          const turn = time * 0.22, cx = x;
          x = cx * Math.cos(turn) - y * Math.sin(turn);
          y = cx * Math.sin(turn) + y * Math.cos(turn);
        }
        const rx = x * Math.cos(yaw) + z * Math.sin(yaw);
        const rz = -x * Math.sin(yaw) + z * Math.cos(yaw);
        const ry = y * Math.cos(pitch) - rz * Math.sin(pitch);
        const depth = y * Math.sin(pitch) + rz * Math.cos(pitch);
        const perspective = 1 / (1 - depth * 0.55);
        return {x: width / 2 + rx * span * perspective,
          y: Math.max(90 + tall / 2, height / 2) + ry * span * perspective,
          depth, radius: Math.max(0.8, 1.5 * perspective), hue: (drone.scene * 38 + i * 0.05) % 360};
      }).sort((a,b) => a.depth - b.depth);
      for (const p of projected) {
        const brightness = Math.max(35, Math.min(78, 57 + p.depth * 65));
        ctx.fillStyle = "hsl(" + p.hue + " 85% " + brightness + "%)";
        ctx.globalAlpha = 0.55 + Math.min(0.45, Math.max(0, p.depth + 0.25));
        ctx.beginPath(); ctx.arc(p.x, p.y, p.radius, 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
    function advance(dt) {
      if (preview) simulated += dt * speed * 1000;
      if (!active()) { rockets = []; sparks = []; groundEffects = []; drone = null; return; }
      if (drone) { advanceDrones(dt); return; }
      fireworksElapsed += dt;
      launchIn -= dt;
      if ((config.drone === false || fireworksElapsed < 120) && launchIn <= 0) { launch(); launchIn = 1.2 + random() * 1.6; }
      if (config.drone !== false && fireworksElapsed >= 120 && !rockets.length && !sparks.length && !groundEffects.length) {
        pendingKind = null; startDrones(); return;
      }
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
        if (drone) drawDrones();
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
        rockets: rockets.length, drone: drone?.name, droneDepthLevels: drone ? new Set(drone.targets.map(p => p.z.toFixed(3))).size : 0, groundEffects: groundEffects.map(e => e.kind), groundSparks: sparks.filter(p => p.ground).length, sound, paused, hidden, zone, show: drone ? "drones" : "fireworks"});
    }
    function tick(now) {
      frame = 0; const dt = Math.min(0.05, previous ? (now - previous) / 1000 : 0); previous = now;
      advance(dt); draw(); syncAudio();
      const inWindow = active();
      canvas.hidden = hidden || !inWindow;
      toggle.hidden = !inWindow; speaker.hidden = !inWindow;
      controls.hidden = !preview && !inWindow;
      frame = requestAnimationFrame(tick);
    }
    function refresh() {
      cancelAnimationFrame(frame); frame = 0; previous = 0;
      const inWindow = active();
      canvas.hidden = hidden || !inWindow; controls.hidden = !preview && !inWindow;
      toggle.hidden = !inWindow; speaker.hidden = !inWindow;
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
      const inSeason = eligible();
      canvas.hidden = hidden || !inSeason; controls.hidden = !inSeason;
      toggle.hidden = !inSeason;
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
