/*
 * Interactive monochrome 3D bar charts (Three.js), used by frontend/charts3d.py inside an isolated iframe.
 *
 * cfg = {
 *   categories: ["1", "2", ...],                 // along X
 *   series: [{ name, shade, values: [...] }],    // along Z (depth) - one row per series
 *   tooltips: [[ "text", ... ], ...],            // per series, per category
 *   xTitle, yTitle, labelEvery, accent: index|null
 * }
 * Drag = rotate, wheel = zoom, "Reset view" = default camera, hover = highlight + tooltip.
 * Renders on demand (only while something moves). No WebGL -> a message pointing to the Table view.
 */
export async function mount(cfg) {
  const root = document.getElementById("wrap");
  const tip = document.getElementById("tip");
  const labels = document.getElementById("labels");
  let THREE;
  try { THREE = await import("/app/static/vendor/three/three.module.js"); }
  catch (e) { return fail("3D library could not load. Use the Table view."); }
  const canvas = document.createElement("canvas");
  root.insertBefore(canvas, root.firstChild);
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false }); }
  catch (e) { canvas.remove(); return fail("3D view needs WebGL, which this browser has turned off. Use the Table view."); }

  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const W = () => root.clientWidth, H = () => root.clientHeight;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x111111);
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 400);

  // ---- layout ----
  const cats = cfg.categories, S = cfg.series, nC = cats.length, nS = S.length;
  const maxV = Math.max(1, ...S.flatMap((s) => s.values));
  const step = 1.0, bw = nC > 30 ? 0.62 : 0.68, depth = 0.68, rowGap = 1.05;
  const width = nC * step, H3 = Math.min(6, Math.max(3.2, width * 0.28));
  const unit = H3 / maxV;
  const x0 = -width / 2 + step / 2, z0 = -((nS - 1) * rowGap) / 2;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x2a2a2a, 1.5));
  scene.add(new THREE.AmbientLight(0xffffff, 0.25));
  const sun = new THREE.DirectionalLight(0xffffff, 2.6);
  sun.position.set(-width * 0.35, H3 * 3, width * 0.6); sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  const sc = Math.max(width, 8);
  Object.assign(sun.shadow.camera, { left: -sc, right: sc, top: sc, bottom: -sc, near: 0.5, far: sc * 6 });
  scene.add(sun);
  const back = new THREE.DirectionalLight(0xffffff, 0.6); back.position.set(width, H3, -width); scene.add(back);

  // floor + grid + back wall ticks (all gray)
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(width + 3, nS * rowGap + 3),
    new THREE.MeshStandardMaterial({ color: 0x161616, roughness: 0.9, metalness: 0.05 }));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  const gridMat = new THREE.LineBasicMaterial({ color: 0x303030 });
  const zBack = z0 - rowGap * 0.6 - 0.4;
  const ints = S.every((s) => s.values.every((v) => Number.isInteger(v)));
  const ticks = niceTicks(maxV, ints);
  const gp = [];
  ticks.forEach((v) => { const y = v * unit; gp.push(-width / 2 - 0.3, y, zBack, width / 2 + 0.3, y, zBack); });
  gp.push(-width / 2 - 0.3, 0, zBack, -width / 2 - 0.3, H3 * 1.05, zBack);
  const gg = new THREE.BufferGeometry(); gg.setAttribute("position", new THREE.Float32BufferAttribute(gp, 3));
  scene.add(new THREE.LineSegments(gg, gridMat));

  // bars
  const geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0.5, 0);
  const bars = [];
  S.forEach((s, si) => {
    s.values.forEach((v, ci) => {
      const shade = s.shade ?? 0xbdbdbd;
      const mat = new THREE.MeshStandardMaterial({ color: shade, roughness: 0.5, metalness: 0.06, emissive: 0x000000 });
      const m = new THREE.Mesh(geo, mat);
      m.position.set(x0 + ci * step, 0, z0 + si * rowGap);
      m.scale.set(bw, Math.max(0.02, v * unit), depth);
      m.castShadow = true; m.receiveShadow = true;
      m.userData = { si, ci, v, target: Math.max(0.02, v * unit), base: shade };
      if (v === 0) { mat.color.setHex(0x1f1f1f); m.castShadow = false; }
      scene.add(m); bars.push(m);
    });
  });

  // ---- HTML labels projected from 3D ----
  const lab = [];
  const addLabel = (text, pos, cls) => { const d = document.createElement("div"); d.className = "lb " + (cls || ""); d.textContent = text;
    labels.appendChild(d); lab.push({ d, p: new THREE.Vector3(...pos) }); };
  const every = cfg.labelEvery || 1;
  cats.forEach((c, ci) => { if (ci % every === 0 || ci === nC - 1) addLabel(c, [x0 + ci * step + (nC > 12 ? 0 : 0.25), -0.02, z0 + (nS - 1) * rowGap + (nC > 12 ? 0.75 : 0.5)], nC > 12 ? "x" : "x cat"); });
  ticks.forEach((v) => addLabel(fmt(v), [-width / 2 - 0.65, v * unit, zBack], "y"));
  if (cfg.yTitle) addLabel(cfg.yTitle, [-width / 2 - 0.3, H3 * 1.16, zBack], "t");
  if (cfg.xTitle) addLabel(cfg.xTitle, [width / 2 + 0.2, -0.02, z0 + (nS - 1) * rowGap + 1.45], "t");
  if (nS > 1) S.forEach((s, si) => addLabel(s.name, [width / 2 + 1.1, 0.02, z0 + si * rowGap], "s"));

  // ---- camera rig ----
  const target = new THREE.Vector3(nC > 16 ? -width * 0.12 : 0, H3 * 0.34, 0);
  const long = nC > 16;                          // long rows recede diagonally so every bar stays readable
  const home = { az: long ? -0.78 : -0.42, el: long ? 0.46 : 0.42, r: 10 };
  const zSpan = nS * rowGap + 1.6;
  const fitRadius = () => {                     // whole chart in view: bounding sphere vs. the narrower fov
    const v = (camera.fov * Math.PI) / 180, h = 2 * Math.atan(Math.tan(v / 2) * camera.aspect);
    const halfW = (width / 2 + 1.3) * Math.cos(home.az) * (long ? 0.82 : 1) + (zSpan / 2) * Math.abs(Math.sin(home.az));
    const halfH = (H3 * 0.62 + 0.8) * Math.cos(home.el) + (zSpan / 2) * Math.sin(home.el);
    return Math.max(halfW / Math.tan(h / 2), halfH / Math.tan(v / 2)) * (long ? 1.3 : 1.12) + zSpan / 2;
  };
  let { az, el, r } = home;
  const place = () => {
    camera.position.set(target.x + r * Math.sin(az) * Math.cos(el), target.y + r * Math.sin(el), target.z + r * Math.cos(az) * Math.cos(el));
    camera.lookAt(target);
  };

  let dirty = true, grow = still ? 1 : 0, t0 = performance.now();
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  let hovered = null, drag = null;

  function render() {
    if (grow < 1) { grow = Math.min(1, (performance.now() - t0) / 700); dirty = true; }
    const g = 1 - Math.pow(1 - grow, 3);
    if (dirty) {
      bars.forEach((b) => { b.scale.y = Math.max(0.02, b.userData.target * g); });
      place();
      renderer.render(scene, camera);
      const w = W(), h = H(), v = new THREE.Vector3();
      lab.forEach(({ d, p }) => { v.copy(p).project(camera);
        const px = (v.x * 0.5 + 0.5) * w, py = (-v.y * 0.5 + 0.5) * h;
        d.style.transform = d.classList.contains("cat")
          ? `translate(${px}px,${py}px) translate(-100%,0) rotate(-32deg)`     // angled, anchored at the bar
          : `translate(-50%,-50%) translate(${px}px,${py}px)`;
        d.style.opacity = v.z < 1 ? "1" : "0"; });
      dirty = grow < 1;
    }
    requestAnimationFrame(render);
  }

  function setHover(m, ev) {
    if (hovered && hovered !== m) { hovered.material.emissive.setHex(0x000000); hovered.material.color.setHex(hovered.userData.v ? hovered.userData.base : 0x1f1f1f); }
    hovered = m;
    if (m) {
      m.material.color.setHex(0xffffff); m.material.emissive.setHex(0x3a3a3a);
      const { si, ci } = m.userData;
      tip.innerHTML = (cfg.tooltips && cfg.tooltips[si] && cfg.tooltips[si][ci]) || `${cats[ci]}: ${fmt(m.userData.v)}`;
      tip.style.opacity = "1";
      const rx = Math.min(ev.offsetX + 14, W() - tip.offsetWidth - 8), ry = Math.max(8, ev.offsetY - tip.offsetHeight - 10);
      tip.style.transform = `translate(${rx}px,${ry}px)`;
      canvas.style.cursor = "pointer";
    } else { tip.style.opacity = "0"; canvas.style.cursor = drag ? "grabbing" : "grab"; }
    dirty = true;
  }

  canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, az, el }; canvas.setPointerCapture(e.pointerId); canvas.style.cursor = "grabbing"; });
  canvas.addEventListener("pointerup", (e) => { drag = null; canvas.releasePointerCapture(e.pointerId); canvas.style.cursor = "grab"; });
  canvas.addEventListener("pointermove", (e) => {
    if (drag) {
      az = drag.az - (e.clientX - drag.x) * 0.006;
      el = Math.max(0.08, Math.min(1.25, drag.el + (e.clientY - drag.y) * 0.005));
      tip.style.opacity = "0"; dirty = true; return;
    }
    const rect = canvas.getBoundingClientRect();
    ptr.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects(bars, false)[0];
    setHover(hit ? hit.object : null, e);
  });
  canvas.addEventListener("pointerleave", () => setHover(null, {}));
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); r = Math.max(home.r * 0.45, Math.min(home.r * 1.8, r * (1 + Math.sign(e.deltaY) * 0.08))); dirty = true; }, { passive: false });
  document.getElementById("reset").addEventListener("click", () => { ({ az, el, r } = home); dirty = true; });

  const resize = () => { renderer.setSize(W(), H(), false); camera.aspect = W() / H(); camera.updateProjectionMatrix();
    const fresh = r === home.r; home.r = fitRadius(); if (fresh) r = home.r; dirty = true; };
  new ResizeObserver(resize).observe(root);
  resize();
  canvas.style.cursor = "grab";
  requestAnimationFrame(render);

  function fail(msg) { const f = document.getElementById("fallback"); f.textContent = msg; f.style.display = "flex"; }
}

function niceTicks(max, ints) {
  const raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / mag;
  const st = Math.max(ints ? 1 : 0, (n >= 5 ? 5 : n >= 2 ? 2 : 1) * mag), out = [];
  for (let v = 0; v <= max + st * 0.001; v += st) out.push(Math.round(v * 1000) / 1000);
  if (out[out.length - 1] < max) out.push(Math.round((out[out.length - 1] + st) * 1000) / 1000);
  return out;
}
function fmt(v) { return v >= 10000 ? (v / 1000).toFixed(0) + "K" : v >= 1000 ? (v / 1000).toFixed(1) + "K" : String(v); }
