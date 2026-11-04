// EDENLOAD — browser bridge
const APP = "http://127.0.0.1:9614";
const bypass = new Set(); // URLs the browser should download itself (app refused them)

async function settings() {
  const s = await chrome.storage.local.get({ intercept: true, minSizeKB: 0 });
  return s;
}

// { alive, capture } — capture is the "Catching on/off" switch in the app
async function appStatus() {
  try {
    const r = await fetch(APP + "/ping", { signal: AbortSignal.timeout(800) });
    if (!r.ok) return { alive: false, capture: false };
    const j = await r.json();
    return { alive: true, capture: j.capture !== false };
  } catch (e) {
    return { alive: false, capture: false };
  }
}

async function appAlive() {
  return (await appStatus()).alive;
}

async function cookieHeader(url) {
  try {
    const cs = await chrome.cookies.getAll({ url });
    return cs.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

async function sendToApp(payload) {
  try {
    const r = await fetch(APP + "/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userAgent: navigator.userAgent, ...payload }),
    });
    return r.ok;
  } catch (e) {
    return false;
  }
}

function baseName(p) {
  return (p || "").split(/[\\/]/).pop();
}

// 1) Catch every download the browser starts and hand it to the app
chrome.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return;            // blob:, data: etc. stay in the browser
  if (bypass.has(url)) { bypass.delete(url); return; }
  const s = await settings();
  if (!s.intercept) return;
  const size = item.totalBytes > 0 ? item.totalBytes : item.fileSize;
  const name = baseName(item.filename).toLowerCase();
  const isTorrent = item.mime === "application/x-bittorrent" || /\.torrent(\?|$)/i.test(url) || name.endsWith(".torrent");
  // .torrent files are tiny, so the size filter never applies to them
  if (!isTorrent && s.minSizeKB && size > 0 && size < s.minSizeKB * 1024) return;
  const st = await appStatus();
  if (!st.alive || !st.capture) return;          // app closed or catching switched off → browser downloads normally

  try { await chrome.downloads.cancel(item.id); } catch (e) {}
  try { await chrome.downloads.erase({ id: item.id }); } catch (e) {}

  const ok = await sendToApp({
    type: isTorrent ? "torrent" : "file",
    url,
    referrer: item.referrer || "",
    filename: baseName(item.filename),
    mime: item.mime || "",
    size: size > 0 ? size : 0,
    cookies: await cookieHeader(url),
  });
  if (!ok) {
    bypass.add(url);
    chrome.downloads.download({ url });
  }
});

// 2) Right-click menus
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "edm-link", title: "Download link with EDENLOAD", contexts: ["link", "image", "audio"] });
    chrome.contextMenus.create({ id: "edm-video", title: "Download video with EDENLOAD", contexts: ["page", "video", "link"] });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "edm-link") {
    const url = info.linkUrl || info.srcUrl;
    if (!url) return;
    if (/^magnet:/i.test(url)) return sendToApp({ type: "torrent", url });
    const isTorrent = /\.torrent(\?|$)/i.test(url);
    await sendToApp({ type: isTorrent ? "torrent" : "file", url, referrer: info.pageUrl || "", cookies: await cookieHeader(url) });
  } else if (info.menuItemId === "edm-video") {
    let url = info.linkUrl || info.pageUrl;
    if (info.srcUrl && /^https?:/i.test(info.srcUrl) && !info.linkUrl) url = info.pageUrl;
    await sendToApp({ type: "video", url, referrer: info.pageUrl || "", title: tab ? tab.title : "" });
  }
});

// 3) Messages from the floating "download video" button and the popup
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.action === "video") {
      const alive = await appAlive();
      if (!alive) return reply({ ok: false, reason: "app" });
      const ok = await sendToApp({ type: "video", url: msg.url, referrer: msg.url, title: msg.title || "" });
      reply({ ok });
    } else if (msg.action === "torrent") {
      const st = await appStatus();               // magnet click = automatic catch, so honour the switch
      if (!st.alive || !st.capture) return reply({ ok: false, reason: st.alive ? "off" : "app" });
      reply({ ok: await sendToApp({ type: "torrent", url: msg.url, referrer: sender.tab ? sender.tab.url : "" }) });
    } else if (msg.action === "status") {
      reply(await appStatus());
    }
  })();
  return true; // async reply
});
