(function () {
  const config = window.OPL_CONFIG && window.OPL_CONFIG.analytics;
  if (!config || !config.enabled) return;

  const path = location.pathname;
  if (config.countEndpoint) {
    const img = new Image(1, 1);
    img.alt = "";
    img.referrerPolicy = "strict-origin-when-cross-origin";
    img.src = config.countEndpoint + "?p=" + encodeURIComponent(path);
  }

  if (config.publicCounterJson) {
    const target = document.querySelector("[data-opl-usage-count]");
    if (!target) return;
    const url = config.publicCounterJson.replace("{path}", encodeURIComponent(path));
    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error("counter unavailable");
        return r.json();
      })
      .then(data => {
        if (data && data.count != null) {
          target.textContent = String(data.count) + " recorded uses";
          target.hidden = false;
        }
      })
      .catch(() => {});
  }
})();
