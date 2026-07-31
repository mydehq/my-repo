function copyInstallCmd() {
  const text = "curl -sL {repo_url}/install | bash";
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.querySelector("#install-step .copy-btn");
    if (!btn) return;

    const iconUse = btn.querySelector("use");

    btn.classList.add("animate-pop");
    if (iconUse) {
      iconUse.setAttribute("href", "assets/icons.svg#icon-check");
    }

    setTimeout(() => btn.classList.remove("animate-pop"), 300);
    setTimeout(() => {
      if (iconUse) {
        iconUse.setAttribute("href", "assets/icons.svg#icon-copy");
      }
    }, 2000);
  });
}

function formatLastUpdated() {
  const lastUpdatedEl = document.getElementById("last-updated");
  if (!lastUpdatedEl) return;

  const isoDate = lastUpdatedEl.innerText.trim();
  const date = new Date(isoDate);

  if (!isNaN(date)) {
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

document.addEventListener("DOMContentLoaded", () => {
  formatLastUpdated();

  const copyBtn = document.querySelector("#install-step .copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", copyInstallCmd);
  }
});
