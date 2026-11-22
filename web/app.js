// Front end: draws the map and replays the steps the Python solver sends back.
// All solving happens on the server (csp/solver.py).

const $ = (s) => document.querySelector(s);
const SVGNS = "http://www.w3.org/2000/svg";

const COLOURS = [
  { name: "Red", hex: "#cf4a3c", on: true },
  { name: "Yellow", hex: "#e8b33a", on: true },
  { name: "Blue", hex: "#3a6ea5", on: true },
  { name: "Green", hex: "#5f9e5a", on: true },
  { name: "Purple", hex: "#8a63a8", on: false },
  { name: "Orange", hex: "#e07b39", on: false },
  { name: "Teal", hex: "#2f9c95", on: false },
  { name: "Pink", hex: "#d77fa1", on: false },
];
const SHORT = { bt: "BT", fc: "BT + FC", mac: "BT + AC-3" };
const NAMES = { bt: "Backtracking", fc: "Forward checking", mac: "Constraint propagation (AC-3)" };

const state = {
  maps: [],
  map: null,          // current map data
  byId: {},
  result: null,       // last /api/solve response
  step: 0,            // how many trace events have been applied
  timer: null,
  view: null,         // what is drawn right now
  shapes: {},         // region id -> [svg elements]
  selected: null,
  compare: null,
};

// ------------------------------------------------------------------ helpers
const chosen = () => COLOURS.filter((c) => c.on);
const hexOf = (name) => (COLOURS.find((c) => c.name === name) || {}).hex || "#999";
const nameOf = (id) => (state.byId[id] ? state.byId[id].name : id);
const method = () => document.querySelector("input[name=method]:checked").value;
const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-IN") : n);

function textOn(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#1f1e1b" : "#fff";
}

async function api(url, body) {
  const res = await fetch(url, body ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  } : undefined);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "request failed");
  return data;
}

// ------------------------------------------------------------------ theme
function setThemeLabel() {
  const dark = document.documentElement.dataset.theme === "dark";
  $("#theme").textContent = dark ? "Light mode" : "Dark mode";
}
$("#theme").onclick = () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = t;
  localStorage.setItem("theme", t);
  setThemeLabel();
};
setThemeLabel();

// ------------------------------------------------------------------ setup panel
function renderMapList() {
  const box = $("#maps");
  box.innerHTML = "";
  for (const m of state.maps) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = state.map && state.map.id === m.id ? "on" : "";
    b.innerHTML = `${m.title.split(" - ")[0]}<span>${m.regions} regions</span>`;
    b.onclick = () => loadMap(m.id);
    box.appendChild(b);
  }
}

function renderColours() {
  const box = $("#colours");
  box.innerHTML = "";
  COLOURS.forEach((c) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (c.on ? " on" : "");
    const pick = document.createElement("input");
    pick.type = "color";
    pick.value = c.hex;
    pick.title = "Change shade";
    pick.oninput = () => { c.hex = pick.value; paint(); };
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = c.name;
    btn.setAttribute("aria-pressed", c.on);
    btn.onclick = () => {
      if (c.on && chosen().length === 1) return; // keep at least one
      c.on = !c.on;
      renderColours();
      settingsChanged();
    };
    chip.append(pick, btn);
    box.appendChild(chip);
  });
  $("#colour-count").textContent = `${chosen().length} selected`;
}

document.querySelectorAll("[data-preset]").forEach((b) => {
  b.onclick = () => {
    const k = +b.dataset.preset;
    COLOURS.forEach((c, i) => (c.on = i < k));
    renderColours();
    settingsChanged();
  };
});
document.querySelectorAll("input[name=method]").forEach((r) => (r.onchange = settingsChanged));

function renderDefinition() {
  if (!state.map) return;
  const regs = state.map.regions;
  const borders = regs.reduce((s, r) => s + r.neighbours.length, 0) / 2;
  $("#def-vars").textContent = `${regs.length} regions`;
  $("#def-dom").innerHTML = `<code>{${chosen().map((c) => c.name).join(", ")}}</code>`;
  $("#def-con").innerHTML = `${borders} neighbour pairs, <code>A &ne; B</code>`;
}

// ------------------------------------------------------------------ map drawing
async function loadMap(id) {
  stop();
  setBusy(true);
  try {
    state.map = await api(`/api/maps/${id}`);
  } finally {
    setBusy(false);
  }
  state.byId = {};
  state.map.regions.forEach((r, i) => { r.order = i + 1; state.byId[r.id] = r; });
  state.selected = null;
  const borders = state.map.regions.reduce((s, r) => s + r.neighbours.length, 0) / 2;
  $("#map-title").textContent = state.map.title;
  $("#map-size").textContent = `${state.map.regions.length} regions / ${borders} borders`;
  $("#map-note").textContent = state.map.note || "";
  renderMapList();
  drawMap();
  settingsChanged();
}

function drawMap() {
  const svg = $("#map");
  const m = state.map;
  svg.setAttribute("viewBox", m.viewBox.join(" "));
  svg.setAttribute("aria-label", m.title);
  svg.innerHTML = "";
  state.shapes = {};

  const gReg = document.createElementNS(SVGNS, "g");
  const gDot = document.createElementNS(SVGNS, "g");
  const gLbl = document.createElementNS(SVGNS, "g");
  const maxArea = Math.max(...m.regions.map((r) => r.area));
  const fontSize = m.viewBox[2] / 78;

  for (const r of m.regions) {
    const p = document.createElementNS(SVGNS, "path");
    p.setAttribute("d", r.path);
    p.setAttribute("class", "region");
    p.dataset.id = r.id;
    gReg.appendChild(p);
    state.shapes[r.id] = [p];

    let lx = r.label[0];
    const ly = r.label[1];
    let outside = false;
    if (r.small || r.area < maxArea * 0.005) {
      // tiny regions (Delhi, Chandigarh...) also get a dot so they can be seen and clicked
      const c = document.createElementNS(SVGNS, "circle");
      c.setAttribute("cx", r.label[0]);
      c.setAttribute("cy", r.label[1]);
      c.setAttribute("r", fontSize * 0.55);
      c.setAttribute("class", "dot region");
      c.dataset.id = r.id;
      gDot.appendChild(c);
      state.shapes[r.id].push(c);
      lx += fontSize * 0.85;
      outside = true;
    }
    const t = document.createElementNS(SVGNS, "text");
    t.setAttribute("x", lx);
    t.setAttribute("y", ly);
    t.setAttribute("class", "lbl");
    t.setAttribute("font-size", fontSize);
    if (outside) { t.style.textAnchor = "start"; t.dataset.out = "1"; }
    t.textContent = r.id;
    gLbl.appendChild(t);
    state.shapes[r.id].push(t);
  }
  svg.append(gReg, gDot, gLbl);
  svg.classList.toggle("no-labels", !$("#labels").checked);
}

$("#labels").onchange = () => $("#map").classList.toggle("no-labels", !$("#labels").checked);

function freshView() {
  const doms = {};
  for (const r of state.map.regions) doms[r.id] = new Set(chosen().map((c) => c.name));
  return { assign: {}, doms, cur: null, clash: [], pruned: null, counts: { nodes: 0, backtracks: 0, pruned: 0 } };
}

function paint() {
  if (!state.map || !state.view) return;
  const v = state.view;
  const nbs = state.selected ? new Set(state.byId[state.selected].neighbours) : new Set();
  for (const r of state.map.regions) {
    const col = v.assign[r.id];
    for (const el of state.shapes[r.id]) {
      if (el.tagName === "text") {
        el.style.fill = col && !el.dataset.out ? textOn(hexOf(col)) : "";
        continue;
      }
      el.style.fill = col ? hexOf(col) : "";
      el.classList.toggle("cur", v.cur === r.id || state.selected === r.id);
      el.classList.toggle("clash", v.clash.includes(r.id));
      el.classList.toggle("pruned", v.pruned === r.id);
      el.classList.toggle("nb", nbs.has(r.id));
    }
  }
}

// ------------------------------------------------------------------ tooltip + click
const tip = $("#tip");
$("#map").addEventListener("mousemove", (e) => {
  const id = e.target.dataset && e.target.dataset.id;
  if (!id) { tip.hidden = true; return; }
  const r = state.byId[id];
  const v = state.view;
  let dom;
  if (v.assign[id]) dom = `Colour: <b style="display:inline">${v.assign[id]}</b>`;
  else {
    const left = [...v.doms[id]];
    dom = left.length ? `Domain: {${left.join(", ")}}` : `<span style="color:var(--bad)">Domain empty</span>`;
  }
  const nb = r.neighbours.length ? r.neighbours.map(nameOf).join(", ") : "none (island)";
  tip.innerHTML = `<b>${r.name}</b><span class="muted">Variable #${r.order} &middot; ${r.id}</span><br>${dom}<br><span class="muted">Neighbours: ${nb}</span>`;
  const box = $(".map-wrap").getBoundingClientRect();
  let x = e.clientX - box.left + 14;
  const y = e.clientY - box.top + 14;
  if (x > box.width - 250) x -= 270;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
  tip.hidden = false;
});
$("#map").addEventListener("mouseleave", () => (tip.hidden = true));
$("#map").addEventListener("click", (e) => {
  const id = e.target.dataset && e.target.dataset.id;
  state.selected = id && state.selected !== id ? id : null;
  paint();
});

// ------------------------------------------------------------------ replaying the trace
function describe(e) {
  const n = (id) => `<b>${nameOf(id)}</b>`;
  switch (e.e) {
    case "try": return `Try ${n(e.v)} = ${e.c}`;
    case "reject": return `${e.c} clashes with ${n(e.w)}, rejected`;
    case "prune": return `Remove ${e.c} from ${n(e.v)}` + (e.by === "AC-3" ? " (initial AC-3)" : ` (because of ${nameOf(e.by)})`);
    case "wipe": return `${n(e.v)} has no colours left, dead end`;
    case "undo": return `Undo ${n(e.v)} = ${e.c}`;
    case "back": return `No colour works for ${n(e.v)}, backtrack`;
    case "done": return `<b>Solution found</b>`;
    case "fail": return `<b>No solution exists</b>`;
    case "stopped": return `<b>Stopped (search limit reached)</b>`;
  }
  return e.e;
}

function apply(e) {
  const v = state.view;
  v.clash = [];
  v.pruned = null;
  switch (e.e) {
    case "try": v.cur = e.v; v.assign[e.v] = e.c; v.counts.nodes++; break;
    case "reject": delete v.assign[e.v]; v.clash = [e.v, e.w]; break;
    case "prune": v.doms[e.v].delete(e.c); v.pruned = e.v; v.counts.pruned++; break;
    case "wipe": v.clash = [e.v]; break;
    case "undo": delete v.assign[e.v]; for (const [id, c] of e.r) v.doms[id].add(c); break;
    case "back": v.cur = e.v; v.counts.backtracks++; break;
    case "done": case "fail": case "stopped": v.cur = null; break;
  }
}

function showStep(e) {
  const total = state.result.trace.length;
  $("#stepno").textContent = `${state.step} / ${total}`;
  $("#status").innerHTML = describe(e);
  const c = state.view.counts;
  if (state.step < total) {
    $("#s-nodes").textContent = fmt(c.nodes);
    $("#s-backtracks").textContent = fmt(c.backtracks);
    $("#s-pruned").textContent = fmt(c.pruned);
  }
}

function stepOnce() {
  const tr = state.result.trace;
  if (state.step >= tr.length) { finish(); return false; }
  const e = tr[state.step++];
  apply(e);
  showStep(e);
  paint();
  if (state.step >= tr.length) finish();
  return state.step < tr.length;
}

async function ensureResult() {
  if (state.result) return true;
  setBusy(true);
  try {
    state.result = await api("/api/solve", { map: state.map.id, colours: chosen().map((c) => c.name), method: method() });
    resetView();
    return true;
  } catch (err) {
    $("#status").textContent = "Error: " + err.message;
    return false;
  } finally {
    setBusy(false);
  }
}

function delay() {
  const s = +$("#speed").value / 100;
  return Math.round(900 * (1 - s) ** 2 + 6);
}

function play() {
  stop();
  const tick = () => {
    if (stepOnce()) state.timer = setTimeout(tick, delay());
    else { state.timer = null; setRunLabel(); }
  };
  state.timer = setTimeout(tick, 0);
  setRunLabel();
}

function stop() {
  if (state.timer) clearTimeout(state.timer);
  state.timer = null;
  setRunLabel();
}

function setRunLabel() {
  const r = state.result;
  const done = r && state.step >= r.trace.length;
  $("#run").textContent = state.timer ? "Pause" : done ? "Replay" : state.step > 0 ? "Resume" : "Solve";
}

function setBusy(b) {
  ["#run", "#step", "#instant", "#compare"].forEach((s) => ($(s).disabled = b));
}

$("#run").onclick = async () => {
  if (state.timer) return stop();
  if (!(await ensureResult())) return;
  if (state.step >= state.result.trace.length) resetView();
  play();
};
$("#step").onclick = async () => {
  stop();
  if (!(await ensureResult())) return;
  stepOnce();
  setRunLabel();
};
$("#instant").onclick = async () => {
  stop();
  if (!(await ensureResult())) return;
  const tr = state.result.trace;
  while (state.step < tr.length) apply(tr[state.step++]);
  if (tr.length) showStep(tr[tr.length - 1]);
  finish();
  paint();
  setRunLabel();
};
$("#reset").onclick = () => { stop(); resetView(); };

function resetView() {
  state.step = 0;
  state.view = freshView();
  $("#banner").hidden = true;
  $("#stepno").textContent = "";
  ["nodes", "backtracks", "checks", "pruned", "time"].forEach((k) => ($("#s-" + k).textContent = "-"));
  $("#status").innerHTML = state.result
    ? `Ready: <b>${NAMES[state.result.method]}</b>, ${state.result.trace.length} steps.`
    : `Press <b>Solve</b> to start, or <b>Step</b> to go one move at a time.`;
  paint();
  setRunLabel();
}

// an odd cycle makes 2 colours impossible; a triangle is the easiest one to point at
function findTriangle() {
  for (const r of state.map.regions) {
    const nb = r.neighbours;
    for (let i = 0; i < nb.length; i++)
      for (let j = i + 1; j < nb.length; j++)
        if (state.byId[nb[i]].neighbours.includes(nb[j])) return [r.id, nb[i], nb[j]];
  }
  return null;
}

function finish() {
  const r = state.result;
  if (!r) return;
  const s = r.stats;
  $("#s-nodes").textContent = fmt(s.nodes);
  $("#s-backtracks").textContent = fmt(s.backtracks);
  $("#s-checks").textContent = fmt(s.checks);
  $("#s-pruned").textContent = fmt(s.pruned);
  $("#s-time").textContent = s.time_ms < 1 ? s.time_ms.toFixed(2) + " ms" : s.time_ms.toFixed(1) + " ms";

  if (r.status === "solved" && r.trace_cut) {
    state.view.assign = { ...r.assignment }; // trace was too long to send in full
  }
  const k = chosen().length;
  const b = $("#banner");
  b.hidden = false;
  if (r.status === "solved") {
    const used = new Set(Object.values(r.assignment)).size;
    b.className = "banner";
    b.innerHTML = `<b>Solved.</b> All ${state.map.regions.length} regions coloured, no two neighbours share a colour (${used} of ${k} colours used).`;
  } else if (r.status === "no_solution") {
    b.className = "banner fail";
    let why = "";
    const tri = k === 2 ? findTriangle() : null;
    if (tri) {
      why = ` For example, ${tri.map(nameOf).join(", ").replace(/, ([^,]*)$/, " and $1")} all border each other, so they need three different colours.`;
      state.view.clash = tri;
      paint();
    }
    b.innerHTML = `<b>No solution with ${k} colour${k > 1 ? "s" : ""}.</b> The solver went through every possibility (${fmt(s.nodes)} assignment${s.nodes === 1 ? "" : "s"}, ${fmt(s.backtracks)} backtrack${s.backtracks === 1 ? "" : "s"}) and reports failure.${why}`;
  } else {
    b.className = "banner fail";
    b.innerHTML = `<b>Stopped.</b> The search limit was reached before an answer was found.`;
  }
}

function settingsChanged() {
  stop();
  state.result = null;
  state.compare = null;
  $("#verdict").hidden = true;
  $("#cmp-table").hidden = true;
  $("#cmp-empty").hidden = false;
  $("#charts").innerHTML = "";
  renderDefinition();
  if (state.map) resetView();
}

// ------------------------------------------------------------------ comparison
$("#compare").onclick = async () => {
  if (!state.map) return;
  setBusy(true);
  $("#compare").textContent = "Running...";
  try {
    state.compare = await api("/api/compare", { map: state.map.id, colours: chosen().map((c) => c.name) });
    renderCompare();
  } catch (err) {
    $("#verdict").hidden = false;
    $("#verdict").textContent = "Error: " + err.message;
  } finally {
    setBusy(false);
    $("#compare").textContent = "Run comparison";
  }
};
$("#rank-by").onchange = () => state.compare && renderCompare();

function renderCompare() {
  const { results, best } = state.compare;
  const key = $("#rank-by").value;
  const win = best[key];
  const k = chosen().length;
  $("#cmp-empty").hidden = true;

  // table
  const tb = $("#cmp-table tbody");
  tb.innerHTML = "";
  const cols = ["nodes", "backtracks", "checks", "pruned", "time_ms"];
  for (const r of results) {
    const tr = document.createElement("tr");
    if (r.method === win) tr.className = "best";
    const label = { solved: "solution", no_solution: "no solution", stopped: "stopped" }[r.status];
    tr.innerHTML = `<td>${r.method_name}</td><td class="res-${r.status}">${label}</td>` +
      cols.map((c) => {
        const val = c === "time_ms" ? r.stats[c].toFixed(2) : fmt(r.stats[c]);
        return `<td class="${best[c] === r.method && c !== "pruned" ? "win" : ""}">${val}</td>`;
      }).join("");
    tb.appendChild(tr);
  }
  $("#cmp-table").hidden = false;

  // verdict
  const label = { nodes: "assignments", backtracks: "backtracks", checks: "constraint checks", time_ms: "ms" }[key];
  const w = results.find((r) => r.method === win);
  const val = (r) => (key === "time_ms" ? r.stats[key].toFixed(2) : fmt(r.stats[key]));
  const others = results.filter((r) => r !== w).map((r) => `${val(r)} for ${SHORT[r.method]}`).join(" and ");
  const ties = results.filter((r) => r !== w && r.stats[key] === w.stats[key]).length;
  const allFail = results.every((r) => r.status === "no_solution");
  let text = `Most optimal here: <b>${NAMES[win]}</b>, with ${val(w)} ${label} against ${others}`;
  text += ties ? " (tie broken by time)." : ".";
  if (allFail) text += ` All three methods correctly report that ${k} colour${k > 1 ? "s are" : " is"} not enough.`;
  $("#verdict").innerHTML = text;
  $("#verdict").hidden = false;

  // small multiples: one bar chart per measure, same three methods in each
  const charts = $("#charts");
  charts.innerHTML = "";
  const titles = { nodes: "Assignments", backtracks: "Backtracks", checks: "Constraint checks", time_ms: "Time (ms)" };
  for (const c of ["nodes", "backtracks", "checks", "time_ms"]) {
    const max = Math.max(...results.map((r) => r.stats[c]), 1e-9);
    const div = document.createElement("div");
    div.className = "chart";
    div.innerHTML = `<h3>${titles[c]}</h3>` + results.map((r) => {
      const pct = (r.stats[c] / max) * 72;
      const shown = c === "time_ms" ? r.stats[c].toFixed(2) : fmt(r.stats[c]);
      return `<div class="bar-row" title="${r.method_name}: ${shown} ${titles[c].toLowerCase()}">
        <span class="who">${SHORT[r.method]}</span>
        <div class="bar-track"><div class="bar${best[c] === r.method ? " win" : ""}" style="width:${pct}%"></div>
        <span class="bar-val" style="left:${pct}%">${shown}</span></div></div>`;
    }).join("");
    charts.appendChild(div);
  }
}

// ------------------------------------------------------------------ start
(async function init() {
  renderColours();
  try {
    state.maps = await api("/api/maps");
    renderMapList();
    await loadMap("india");
  } catch (err) {
    $("#status").textContent = "Could not reach the Python server. Start it with: python app.py";
  }
})();
