(() => {
  const installButtons = [...document.querySelectorAll("[data-install-opl]")];
  let deferredPrompt = null;

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      const swUrl = new URL("sw.js", document.querySelector('link[rel="manifest"]').href);
      navigator.serviceWorker.register(swUrl.href).catch(() => {});
    });
  }

  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    deferredPrompt = event;
    installButtons.forEach(button => {
      button.hidden = false;
      button.disabled = false;
    });
  });

  installButtons.forEach(button => {
    button.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      button.hidden = true;
    });
  });

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    installButtons.forEach(button => { button.hidden = true; });
  });
})();
