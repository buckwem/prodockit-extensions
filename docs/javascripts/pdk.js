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
