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

  // Clipboard Copy with Icon Swap
  const copyBtn = document.querySelector("#install-step .copy-btn");
  if (copyBtn) {
    let resetTimer = null;

    copyBtn.addEventListener("click", () => {
      const cmdText = document
        .querySelector("#install-step .font-monospace")
        ?.innerText.trim();

      if (!cmdText) return;

      navigator.clipboard.writeText(cmdText).then(() => {
        const iconUse = copyBtn.querySelector("use");

        if (iconUse) {
          iconUse.setAttribute("href", "src/icons.svg#icon-check");
        }

        // Reset timer on rapid consecutive clicks
        if (resetTimer) clearTimeout(resetTimer);

        resetTimer = setTimeout(() => {
          if (iconUse) {
            iconUse.setAttribute("href", "src/icons.svg#icon-copy");
          }
        }, 2000);
      });
    });
  }
});
