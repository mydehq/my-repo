document.addEventListener("DOMContentLoaded", () => {
  // Format Unix Epoch Timestamp
  const lastUpdatedEl = document.getElementById("last-updated");

  if (lastUpdatedEl) {
    const rawValue = parseInt(lastUpdatedEl.innerText.trim(), 10);

    // Auto-detect seconds vs milliseconds (10-digit vs 13-digit)
    const date = new Date(rawValue > 1e11 ? rawValue : rawValue * 1000);

    if (!isNaN(date.getTime())) {
      const dateStr = date.toLocaleDateString(undefined, {
        month: "short",
        day: "2-digit",
        year: "numeric",
      });
      const timeStr = date.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });

      lastUpdatedEl.innerHTML = `${dateStr} <span class="time-separator">@</span> ${timeStr}`;
    }
  }

  // ── Generic copy helper with icon swap ──
  async function copyWithFeedback(btn, text) {
    const iconUse = btn.querySelector("use");
    const originalHref = iconUse?.getAttribute("href");
    const originalTitle = btn.getAttribute("title");
    const originalLabel = btn.getAttribute("aria-label");
    const alreadyGreen = btn.classList.contains("text-green");

    if (iconUse) iconUse.setAttribute("href", "src/icons.svg#icon-check");
    btn.classList.add("text-green", "animate-pop");

    try {
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
        await navigator.clipboard.writeText(text);
      } catch {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.setAttribute("readonly", "");
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.append(textArea);
        textArea.select();
        const copied = document.execCommand("copy");
        textArea.remove();
        if (!copied) throw new Error("Clipboard copy failed");
      }

    } catch {
      if (iconUse) iconUse.setAttribute("href", "src/icons.svg#icon-x");
      btn.setAttribute("title", "Copy failed");
      btn.setAttribute("aria-label", "Copy failed");
    }

    if (btn._resetTimer) clearTimeout(btn._resetTimer);
    btn._resetTimer = setTimeout(() => {
      if (iconUse && originalHref) iconUse.setAttribute("href", originalHref);
      if (!alreadyGreen) btn.classList.remove("text-green");
      btn.classList.remove("animate-pop");
      if (originalTitle === null) btn.removeAttribute("title");
      else btn.setAttribute("title", originalTitle);
      if (originalLabel === null) btn.removeAttribute("aria-label");
      else btn.setAttribute("aria-label", originalLabel);
    }, 3000);
  }

  // ── Install command copy ──
  const copyBtn = document.querySelector("#install-step .copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const cmdText = document
        .querySelector("#install-step .font-monospace")
        ?.innerText.trim();
      if (cmdText) copyWithFeedback(copyBtn, cmdText);
    });
  }

  // ── Per-row install copy (event delegation) ──
  const packageList = document.getElementById("package-list");
  if (packageList) {
    packageList.addEventListener("click", (e) => {
      const btn = e.target.closest(".pkg-copy-btn");
      if (!btn) return;

      const pkgName = btn.dataset.pkg;
      if (pkgName) {
        copyWithFeedback(btn, `sudo pacman -S ${pkgName}`);
      }
    });
  }

  // ── Package search / filter ──
  const searchInput = document.getElementById("pkg-search");
  const searchBox = document.getElementById("pkg-search-box");
  const searchBtn = document.getElementById("pkg-search-btn");
  const searchClose = document.getElementById("pkg-search-close");
  const headerRow = document.querySelector(".pkg-header-row");
  const packageScroller = packageList;

  function openSearch({ focusInput = true, scrollIntoView = true } = {}) {
    if (!searchBox) return;
    headerRow?.classList.add("search-active");
    if (searchBtn) searchBtn.style.display = "none";
    searchBox.style.display = "flex";
    searchBox.classList.add("show");

    if (focusInput) {
      searchInput?.focus({ preventScroll: true });
      searchInput?.select();
    }

    if (scrollIntoView) {
      headerRow?.scrollIntoView({ behavior: "smooth", block: "start" });
      packageScroller?.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function closeSearch() {
    if (!searchBox) return;
    headerRow?.classList.remove("search-active");
    searchBox.classList.remove("show");
    searchBox.style.display = "none";
    if (searchBtn) searchBtn.style.display = "";
    if (searchInput) {
      searchInput.value = "";
      filterPackages("");
      updateSearchUrl("");
    }
    searchBtn?.focus();
  }

  function filterPackages(rawQuery) {
    const query = (rawQuery || "").toLowerCase().trim();
    if (!packageList) return;

    const noResultsRow = packageList.querySelector(".no-results-row");
    const pkgRows = packageList.querySelectorAll(".pkg-row");

    let visibleCount = 0;
    pkgRows.forEach((row) => {
      const text = (row.textContent || "").toLowerCase();
      const matches = !query || text.includes(query);
      row.style.display = matches ? "" : "none";
      if (matches) visibleCount++;
    });

    if (noResultsRow) {
      noResultsRow.style.display =
        query && visibleCount === 0 ? "flex" : "none";
    }
  }

  function updateSearchUrl(rawQuery) {
    const url = new URL(window.location.href);
    const query = rawQuery.trim();

    if (query) url.searchParams.set("search", query);
    else url.searchParams.delete("search");

    window.history.replaceState(null, "", url);
  }

  if (searchBtn) {
    searchBtn.addEventListener("click", openSearch);
  }

  if (searchClose) {
    searchClose.addEventListener("click", closeSearch);
  }

  // Keyboard shortcut: '/' to open, 'Escape' to close
  document.addEventListener("keydown", (e) => {
    const isOpen = searchBox && searchBox.style.display === "flex";
    if (e.key === "Escape" && isOpen) {
      closeSearch();
    } else if (
      e.key === "/" &&
      !isOpen &&
      !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)
    ) {
      e.preventDefault();
      openSearch();
    }
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      filterPackages(searchInput.value);
      updateSearchUrl(searchInput.value);

      // Smoothly scroll to the package list on search if scrolled away
      if (searchInput.value.trim()) {
        const pkgSection = document.getElementById("packages");
        if (pkgSection && window.scrollY < pkgSection.offsetTop - 120) {
          pkgSection.scrollIntoView({ behavior: "smooth" });
        }
      }
    });

    const initialQuery = new URLSearchParams(window.location.search)
      .get("search")
      ?.trim();
    if (initialQuery) {
      searchInput.value = initialQuery;
      openSearch({ focusInput: false, scrollIntoView: false });
      filterPackages(initialQuery);
    }
  }
});
