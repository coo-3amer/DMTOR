const defaults = { intercept: true, videoButton: true, magnets: true, minSizeKB: 0 };

chrome.storage.local.get(defaults, (s) => {
  for (const id of ["intercept", "videoButton", "magnets"]) {
    const el = document.getElementById(id);
    el.checked = s[id];
    el.addEventListener("change", () => chrome.storage.local.set({ [id]: el.checked }));
  }
  const min = document.getElementById("minSizeKB");
  min.value = s.minSizeKB;
  min.addEventListener("change", () => chrome.storage.local.set({ minSizeKB: Math.max(0, +min.value || 0) }));
});

chrome.runtime.sendMessage({ action: "status" }, (res) => {
  const st = document.getElementById("st");
  const text = document.getElementById("sttext");
  if (res && res.alive && res.capture === false) { text.textContent = "Connected — catching is off in the app"; st.className = "status paused"; }
  else if (res && res.alive) { text.textContent = "Connected to DMTOR"; st.className = "status on"; }
  else { text.textContent = "App is not running"; st.className = "status off"; }
});
