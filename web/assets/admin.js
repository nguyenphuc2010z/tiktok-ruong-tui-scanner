(() => {
  let pw = sessionStorage.getItem("admin_pw") || "";
  const $ = (id) => document.getElementById(id);
  const loginView = $("loginView"), dashView = $("dashView");

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2200);
  }
  function hdr() { return { "Content-Type": "application/json", "X-Admin-Pass": pw }; }

  async function api(path, opts = {}) {
    const r = await fetch(path, { ...opts, headers: { ...hdr(), ...(opts.headers || {}) } });
    if (r.status === 401) { logout(); throw new Error("401"); }
    return r.json();
  }

  function logout() {
    pw = ""; sessionStorage.removeItem("admin_pw");
    dashView.classList.add("hidden"); loginView.classList.remove("hidden");
  }

  async function login() {
    const v = $("pw").value;
    try {
      const r = await fetch("/api/admin/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: v }),
      });
      if (!r.ok) { toast("Sai mật khẩu"); return; }
      pw = v; sessionStorage.setItem("admin_pw", v);
      loginView.classList.add("hidden"); dashView.classList.remove("hidden");
      loadAll();
    } catch (e) { toast("Lỗi kết nối"); }
  }

  async function loadSettings() {
    const s = await api("/api/admin/settings");
    $("tgToken").value = s.telegram_token || "";
    $("tgChat").value = s.telegram_chat || "";
    $("tgEnabled").value = s.telegram_enabled === "1" ? "1" : "0";
    $("minCoins").value = s.min_coins || 0;
    $("minRatio").value = s.min_ratio || 0;
    $("minViewers").value = s.min_viewers || 0;
    $("types").value = s.types || "ruong,tui";
    $("levels").value = s.levels || "";
    $("pollInterval").value = s.poll_interval || 20;
    $("discoverInterval").value = s.discover_interval || 90;
    $("maxRooms").value = s.max_rooms || 300;
    $("seeds").value = s.seeds || "";
  }

  async function loadStatus() {
    try {
      const st = await api("/api/admin/status");
      $("sRunning").innerHTML = `<span class="dot-on ${st.running ? "" : "dot-off"}"></span>${st.running ? "Đang quét" : "Đã dừng"}`;
      $("sTracked").textContent = st.live_tracked;
      $("sLive").textContent = st.stats.live;
      $("s24").textContent = st.stats.detections_24h;
      $("sTotal").textContent = st.stats.detections_total;
    } catch (e) {}
  }

  async function loadLogs() {
    try {
      const logs = await api("/api/admin/logs?limit=200");
      $("logs").innerHTML = logs.map((l) => {
        const t = new Date(l.ts * 1000).toLocaleTimeString("vi-VN");
        return `<div class="log-line ${l.level}"><span class="t">${t}</span><span class="m">${escapeHtml(l.message)}</span></div>`;
      }).join("") || '<div class="log-line"><span class="m">Chưa có nhật ký.</span></div>';
    } catch (e) {}
  }

  function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

  async function save() {
    const body = {
      telegram_token: $("tgToken").value.trim(),
      telegram_chat: $("tgChat").value.trim(),
      telegram_enabled: $("tgEnabled").value,
      min_coins: $("minCoins").value || 0,
      min_ratio: $("minRatio").value || 0,
      min_viewers: $("minViewers").value || 0,
      types: $("types").value,
      levels: $("levels").value,
      poll_interval: $("pollInterval").value || 20,
      discover_interval: $("discoverInterval").value || 90,
      max_rooms: $("maxRooms").value || 300,
      seeds: $("seeds").value,
    };
    const np = $("adminPw").value.trim();
    if (np) body.admin_password = np;
    await api("/api/admin/settings", { method: "POST", body: JSON.stringify(body) });
    if (np) { pw = np; sessionStorage.setItem("admin_pw", np); $("adminPw").value = ""; }
    toast("Đã lưu cấu hình");
    loadStatus();
  }

  async function testTg() {
    const token = $("tgToken").value.trim(), chat = $("tgChat").value.trim();
    if (!token || !chat) { toast("Nhập token & chat id trước"); return; }
    try {
      const r = await api("/api/admin/test-telegram", { method: "POST", body: JSON.stringify({ token, chat }) });
      toast(r.ok ? "Đã gửi tin thử về Telegram" : "Gửi thất bại — kiểm tra token/chat id");
    } catch (e) { toast("Lỗi gửi thử"); }
  }

  async function checkChannel() {
    const v = ($("checkInput").value || "").trim();
    const box = $("checkResult");
    if (!v) { box.textContent = "Nhập username hoặc link TikTok trước."; return; }
    box.textContent = "⏳ Đang kiểm tra...";
    try {
      const r = await api("/api/admin/check-channel", {
        method: "POST", body: JSON.stringify({ value: v }),
      });
      if (!r.ok) { box.textContent = "❌ " + (r.message || "Không kiểm tra được"); return; }
      let txt = `✅ Username: @${r.username}\n`;
      if (!r.live) {
        txt += "🔴 Hiện KHÔNG phát LIVE — vẫn có thể thêm vào danh sách, hệ thống sẽ dò lại sau.";
      } else {
        txt += `🟢 Đang LIVE — ${r.viewers ? Number(r.viewers).toLocaleString("vi-VN") + " người xem" : ""}\n`;
        if (r.title) txt += `📝 ${r.title}\n`;
        txt += r.prizes && r.prizes.length
          ? `🎁 Có ${r.prizes.length} rương/túi: ` + r.prizes.map(p => `${p.kind === "ruong" ? "Rương" : "Túi"} ${p.coins} xu`).join(", ")
          : "⚪ Chưa có rương/túi trong phòng này";
      }
      box.style.whiteSpace = "pre-line";
      box.textContent = txt;
      if (r.username) {
        const ta = $("seeds");
        const lines = ta.value.split("\n").map(s => s.trim()).filter(Boolean);
        if (!lines.some(l => l.replace(/^@/, "").split("/").pop() === r.username)) {
          lines.push(r.username);
          ta.value = lines.join("\n");
          toast("Đã thêm @" + r.username + " vào danh sách — nhớ bấm Lưu");
        }
      }
    } catch (e) {
      box.textContent = "❌ Lỗi kết nối";
    }
  }

  async function scannerAction(action) {
    await api("/api/admin/scanner", { method: "POST", body: JSON.stringify({ action }) });
    toast(action === "start" ? "Đã bật quét" : "Đã dừng quét");
    loadStatus();
  }

  async function loadAll() { await loadSettings(); await loadStatus(); await loadLogs(); }

  $("loginBtn").addEventListener("click", login);
  $("pw").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
  $("btnSave").addEventListener("click", save);
  $("btnCheck").addEventListener("click", checkChannel);
  $("checkInput").addEventListener("keydown", (e) => { if (e.key === "Enter") checkChannel(); });
  $("btnTestTg").addEventListener("click", testTg);
  $("btnStart").addEventListener("click", () => scannerAction("start"));
  $("btnStop").addEventListener("click", () => scannerAction("stop"));
  $("btnRefresh").addEventListener("click", loadAll);

  // auto-login if stored
  if (pw) {
    api("/api/admin/status").then(() => {
      loginView.classList.add("hidden"); dashView.classList.remove("hidden"); loadAll();
    }).catch(() => logout());
  }
  setInterval(() => { if (!dashView.classList.contains("hidden")) { loadStatus(); loadLogs(); } }, 5000);
})();
