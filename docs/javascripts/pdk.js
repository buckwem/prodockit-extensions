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
      ? Math.max(120, Number(root.dataset.carouselMinWidth)) : 224;
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
        pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, drag: 0};
        suppressClick = false;
        schedule();
      });
      on(root, "pointermove", event => {
        if (!pointer || pointer.id !== event.pointerId) return;
        const dx = event.clientX - pointer.x;
        const dy = event.clientY - pointer.y;
        if (Math.abs(dx) <= Math.abs(dy) || Math.abs(dx) < 8) return;
        if (!root.hasPointerCapture(event.pointerId)) root.setPointerCapture(event.pointerId);
        pointer.drag = Math.max(!loop && atEnd() ? 0 : -stride, Math.min(!loop && start === 0 ? 0 : stride, dx));
        suppressClick = true;
        root.classList.add("pdk-carousel-dragging");
        list.style.transform = `translateX(${offset + pointer.drag}px)`;
        event.preventDefault();
      });
      function release(event, cancelled = false) {
        if (!pointer || pointer.id !== event.pointerId) return;
        const drag = pointer.drag;
        pointer = null;
        root.classList.remove("pdk-carousel-dragging");
        if (root.hasPointerCapture(event.pointerId)) root.releasePointerCapture(event.pointerId);
        if (!cancelled && Math.abs(drag) > Math.min(50, stride / 4)) move(drag < 0 ? 1 : -1, true, drag);
        else { list.style.transform = `translateX(${offset}px)`; schedule(); }
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
