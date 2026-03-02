const svg = d3.select("#svg");
const metaEl = document.getElementById("meta");
const colorByEl = document.getElementById("colorBy");
const refreshBtn = document.getElementById("refreshBtn");
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const detailRoot = document.getElementById("detailRoot");
const nodeBadge = document.getElementById("nodeBadge");

let gRoot = null;
let rootHierarchy = null;
let nodeIndex = new Map(); // id -> d3 node
let selectedId = null;
let lastTreePayload = null;

// ----- Zoom / Pan (do not reset on selection) -----
const zoom = d3.zoom()
  .scaleExtent([0.12, 4])
  .on("zoom", (event) => {
    if (gRoot) gRoot.attr("transform", event.transform);
  });

svg.call(zoom);
// Prevent wheel from scrolling the page while hovering the SVG
svg.on("wheel", (event) => {
  event.preventDefault();
}, { passive: false });

// ----- Helpers -----
function fmt(x) {
  if (x === null || x === undefined) return "N/A";
  if (typeof x === "number") {
    if (!Number.isFinite(x)) return "N/A";
    const s = x.toString();
    if (s.includes(".")) return x.toFixed(4);
    return s;
  }
  return String(x);
}

function nodeRadius(d) {
  // Smoother & bigger than before, but capped.
  const v = d.data.visits;
  const base = 10;
  const vv = (v && v > 0) ? v : 0;

  // log scale: visits 1 -> ~10, 10 -> ~15, 100 -> ~19
  let r = base + Math.log10(vv + 1) * 6.0;

  // stage styling
  if (d.data.id === "__root__") r += 4;
  if (d.data.has_submission) r += 1.5;
  if (d.data.is_buggy) r += 1.5;

  return Math.max(8, Math.min(22, r));
}

function nodeLabel(d) {
  // requirement: if no metric => show N/A (not node id)
  const m = d.data.metric;
  if (m === null || m === undefined || Number.isNaN(m)) return "N/A";
  return fmt(+m);
}

function colorScaleBy(field, nodes) {
  const vals = nodes
    .map(n => n.data[field])
    .filter(v => v !== null && v !== undefined && !Number.isNaN(v))
    .map(v => +v);

  if (vals.length === 0) return () => "#7a6cff";

  const min = d3.min(vals);
  const max = d3.max(vals);
  const domain = (min === max) ? [min - 1e-9, max + 1e-9] : [min, max];
  return d3.scaleSequential(d3.interpolatePlasma).domain(domain);
}

async function fetchTree(refresh=false) {
  const url = refresh ? "/api/tree?refresh=1" : "/api/tree";
  const res = await fetch(url);
  if (!res.ok) throw new Error("failed to load tree");
  return await res.json();
}

async function fetchNode(id) {
  const res = await fetch(`/api/node/${id}`);
  if (!res.ok) return { error: "node not found", id };
  return await res.json();
}

function setMeta(info) {
  const s = info.stats || {};
  metaEl.textContent =
    `run_dir=${info.run_dir} | nodes=${fmt(s.parsed_nodes)} | files=${fmt(s.total_files)} | roots=${fmt(s.roots)} | depth=${fmt(s.max_depth)} | missing_parents=${fmt(s.missing_parents)}`;
}

// ----- Detail rendering (structured, no stdout, code at end) -----
function clearDetail() {
  nodeBadge.textContent = "none";
  detailRoot.className = "detailEmpty";
  detailRoot.textContent = "点击左侧任意节点查看详情。";
}

function makeCard(title, value, isCode=false) {
  const wrap = document.createElement("div");
  wrap.className = "card";

  const t = document.createElement("div");
  t.className = "cardTitle";
  t.textContent = title;

  wrap.appendChild(t);

  if (isCode) {
    const pre = document.createElement("pre");
    pre.className = "codeBlock";
    pre.textContent = value || "";
    wrap.appendChild(pre);
  } else {
    const v = document.createElement("div");
    v.className = "cardValue";
    v.textContent = value;
    wrap.appendChild(v);
  }
  return wrap;
}

function renderDetail(nodeJson) {
  // preserve visualization; only update the side panel
  nodeBadge.textContent = nodeJson?.id ? nodeJson.id.slice(0, 8) : "unknown";

  // Root container
  const grid = document.createElement("div");
  grid.className = "detailGrid";

  // Drop stdout, move code to end
  const dropKeys = new Set(["stdout"]);
  const code = nodeJson?.code;

  // Preferred order first
  const order = [
    "id", "stage", "parent",
    "metric", "maximize",
    "uct_value", "visits",
    "reward", "total_reward",
    "is_buggy", "has_submission",
    "submission_file"
  ];

  const present = new Set(Object.keys(nodeJson || {}));

  // Render ordered fields
  for (const k of order) {
    if (!present.has(k) || dropKeys.has(k) || k === "code") continue;
    const val = nodeJson[k];
    grid.appendChild(makeCard(k, (typeof val === "object" ? JSON.stringify(val, null, 2) : fmt(val))));
  }

  // Render remaining fields (except dropped and code)
  for (const k of Object.keys(nodeJson || {})) {
    if (order.includes(k) || dropKeys.has(k) || k === "code") continue;
    const val = nodeJson[k];
    grid.appendChild(makeCard(k, (typeof val === "object" ? JSON.stringify(val, null, 2) : fmt(val))));
  }

  // code last
  if (code !== undefined) {
    grid.appendChild(makeCard("code", String(code), true));
  }

  // replace panel
  detailRoot.className = "";
  detailRoot.innerHTML = "";
  detailRoot.appendChild(grid);
}

// ----- Render tree (no re-render on selection) -----
function clearCanvas() {
  svg.selectAll("*").remove();
  gRoot = svg.append("g");
}

function render(treePayload) {
  lastTreePayload = treePayload;
  clearCanvas();

  rootHierarchy = d3.hierarchy(treePayload.tree);
// Top-down layout: x = horizontal, y = vertical
  const treeLayout = d3.tree().nodeSize([110, 160]); // 间距更大：xSpacing, ySpacing
  treeLayout(rootHierarchy);

  const nodes = rootHierarchy.descendants();
  const links = rootHierarchy.links();

  nodeIndex = new Map();
  nodes.forEach(n => nodeIndex.set(n.data.id, n));

  const field = colorByEl.value;
  const scale = colorScaleBy(field, nodes);

  // ---- links (vertical) ----
  gRoot.selectAll(".link")
  .data(links)
  .enter()
  .append("path")
  .attr("class", "link")
  .attr("d", d3.linkVertical()
      .x(d => d.x)
      .y(d => d.y)
  );

  // ---- nodes ----
  const nodeG = gRoot.selectAll(".node")
  .data(nodes, d => d.data.id)
  .enter()
  .append("g")
  .attr("class", d => "node" + (d.data.id === selectedId ? " selected" : ""))
  .attr("transform", d => `translate(${d.x},${d.y})`)
  .on("click", async (event, d) => {
      event.stopPropagation();
      await selectNode(d.data.id);
  });

  nodeG.append("circle")
  .attr("r", d => nodeRadius(d))
  .attr("fill", d => {
      if (d.data.id === "__root__") return "#404a66";
      if (d.data.is_buggy) return "#ff4d6d";

      const v = d.data[field];
      if (v === null || v === undefined || Number.isNaN(v)) return "#6a5cff";
      return scale(+v);
  })
  .attr("opacity", d => (d.data.id === "__root__" ? 0.7 : 0.92));

  // ✅ label：metric 或 N/A（必须有）
  nodeG.append("text")
  .attr("text-anchor", "middle")
  .attr("dominant-baseline", "middle") // 比 dy 更稳定
  .text(d => nodeLabel(d));

  // NOTE: we intentionally do NOT attach svg background click to re-render or reset zoom.
  // If you want "click blank to clear selection", we clear selection only:
  svg.on("click", () => {
    selectedId = null;
    svg.selectAll(".node").classed("selected", false);
    clearDetail();
  });
}

async function selectNode(id) {
  selectedId = id;

  // highlight selected; NO re-render, NO zoom change
  svg.selectAll(".node").classed("selected", d => d.data.id === selectedId);

  const data = await fetchNode(id);
  renderDetail(data);
}

async function bootstrap(refresh=false) {
  const payload = await fetchTree(refresh);
  setMeta(payload);

  // First render only. Keep existing zoom transform if user already navigated.
  // We do not call zoom.transform() here to avoid "jump back" behavior.
  const hadTransform = svg.__zoom ? true : false;
  render(payload);

  // If never zoomed yet, set a mild initial translate once.
  if (!hadTransform) {
    const initial = d3.zoomIdentity.translate(60, 40).scale(1.0);
    svg.call(zoom.transform, initial);
  }
}

refreshBtn.addEventListener("click", async () => {
  // refresh data but keep zoom; since render() rebuilds DOM, current transform remains applied by zoom handler.
  await bootstrap(true);
});

colorByEl.addEventListener("change", async () => {
  await bootstrap(false);
});

searchBtn.addEventListener("click", async () => {
  const q = (searchInput.value || "").trim();
  if (!q) return;

  // match by prefix (first match)
  let found = null;
  for (const [id] of nodeIndex.entries()) {
    if (id.startsWith(q)) { found = id; break; }
  }
  if (!found) {
    renderDetail({ error: "no match", query: q });
    return;
  }
  await selectNode(found);
});

// init
clearDetail();
bootstrap(false).catch(err => {
  renderDetail({ error: String(err) });
});
