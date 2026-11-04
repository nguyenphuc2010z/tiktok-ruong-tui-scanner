(() => {
  const grid = document.getElementById("liveGrid");
  const state = { type: "all", minCoins: 0, minRatio: 0, auto: true, items: [] };
  let timer = null;

  const fmt = (n) => (n || 0).toLocaleString("vi-VN");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  function countdown(sec) {
    if (sec <= 0) return "Đang mở";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function card(it) {
    const isTui = it.kind === "tui";
    const kindLabel = isTui ? "👜 TÚI" : "🎁 RƯƠNG";
    const level = it.level != null ? `Lv${it.level}` : "";
    const av = it.avatar || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48'%3E%3Crect width='48' height='48' fill='%23222'/%3E%3C/svg%3E";
    return `
    <article class="card ${isTui ? "tui" : ""}" data-open="${it.open_ts}">
      <div class="card-top">
        <img class="avatar" src="${esc(av)}" alt="" loading="lazy" onerror="this.style.opacity=.3" />
        <div class="who">
          <div class="name">${esc(it.nickname)}</div>
          <div class="uid">@${esc(it.unique_id)}</div>
        </div>
        <span class="badge ${isTui ? "tui" : "ruong"}">${kindLabel} ${level}</span>
      </div>
      <div class="card-title">${esc(it.title || "Phòng LIVE TikTok")}</div>
      <div class="metrics">
        <div class="metric coins"><b>${fmt(it.coins)}</b><span>Xu</span></div>
        <div class="metric"><b>${it.winners ? fmt(it.winners) : "?"}</b><span>Suất</span></div>
        <div class="metric ratio"><b>${it.ratio ?? 0}</b><span>Ratio</span></div>
      </div>
      <div class="card-foot">
        <div>
          <div class="count" data-cd="${it.open_ts}"><span class="k">Mở sau</span> <span class="cdv">${countdown(it.countdown)}</span></div>
          <div class="viewers">👀 ${fmt(it.viewers)} người xem</div>
        </div>
        <a class="open-btn" href="${esc(it.link)}" target="_blank" rel="noopener">Mở LIVE ↗</a>
      </div>
    </article>`;
  }

  function render() {
    if (!state.items.length) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <div class="big">🔍</div>
        <div>Chưa có phòng LIVE nào đang có rương/túi phù hợp bộ lọc.</div>
        <div style="margin-top:6px;font-size:13px">Hệ thống vẫn đang quét liên tục — danh sách sẽ tự xuất hiện khi có kèo.</div>
      </div>`;
      return;
    }
    grid.innerHTML = state.items.map(card).join("");
  }

  function tick() {
    document.querySelectorAll("[data-cd]").forEach((el) => {
      const open = parseInt(el.getAttribute("data-cd"), 10);
      const left = Math.max(0, open - Math.floor(Date.now() / 1000));
      const v = el.querySelector(".cdv");
      if (v) v.textContent = countdown(left);
      el.classList.toggle("hot", left > 0 && left <= 30);
    });
  }

  async function load() {
    try {
      const q = new URLSearchParams({
        type: state.type, min_coins: state.minCoins, min_ratio: state.minRatio, limit: 100,
      });
      const r = await fetch(`/api/live?${q}`, { cache: "no-store" });
      const d = await r.json();
      state.items = d.items || [];
      render();
      if (d.stats) {
        document.getElementById("statLive").textContent = fmt(d.stats.live);
        document.getElementById("stat24").textContent = fmt(d.stats.detections_24h);
        document.getElementById("statTotal").textContent = fmt(d.stats.detections_total);
      }
    } catch (e) {
      console.error(e);
    }
  }

  // tabs
  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      state.type = t.dataset.type;
      load();
    });
  });

  const fCoins = document.getElementById("fCoins");
  const fRatio = document.getElementById("fRatio");
  let deb;
  const onFilter = () => {
    clearTimeout(deb);
    deb = setTimeout(() => {
      state.minCoins = parseInt(fCoins.value, 10) || 0;
      state.minRatio = parseFloat(fRatio.value) || 0;
      load();
    }, 300);
  };
  fCoins.addEventListener("input", onFilter);
  fRatio.addEventListener("input", onFilter);

  document.getElementById("autoRefresh").addEventListener("change", (e) => {
    state.auto = e.target.checked;
    if (state.auto) start(); else stop();
  });

  function start() {
    stop();
    timer = setInterval(load, 8000);
  }
  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  setInterval(tick, 1000);
  load();
  start();
})();
