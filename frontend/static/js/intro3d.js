/*
 * AI Promo Intelligence Studio - five-second cinematic introduction (Three.js, monochrome).
 *
 * Scene: a black studio. A brushed-metal film reel (extruded flanges with cut-outs, matte film coil,
 * hub) is revealed by a white key light and turns; a sprocketed film strip flows off the reel along a
 * 3D curve; screenplay pages rise into frame; an editorial timeline draws in with three clip markers;
 * the camera dollies through; the product name lands; the overlay dissolves into the dashboard.
 *
 * Loaded by frontend/intro.py as <script type="module" src="/app/static/js/intro3d.js?force=0|1&n=...">.
 * Shown once per browser (localStorage), skippable (button / Esc), reduced-motion aware, with a CSS
 * fallback when WebGL or Three.js is unavailable. Any error removes the overlay - the app always loads.
 */
const params = new URL(import.meta.url).searchParams;
const FORCE = params.get("force") === "1";
const NONCE = params.get("n") || "0";
const KEY = "apis.intro.v2";
const DURATION = 5.0;            // seconds of animation
const FREEZE = params.has("freeze") ? parseFloat(params.get("freeze")) : null;   // QA only: render one frame at t
const doc = document;

function storage(kind) { try { return window[kind]; } catch (e) { return null; } }
const local = storage("localStorage"), sess = storage("sessionStorage");

(function guard() {
  if (!FORCE && local && local.getItem(KEY)) return;
  if (sess) { if (sess.getItem("ap3d-" + NONCE)) return; sess.setItem("ap3d-" + NONCE, "1"); }
  if (doc.getElementById("ap3d")) return;
  run().catch(() => { const o = doc.getElementById("ap3d"); if (o) o.remove(); });
})();

function css() {
  const s = doc.createElement("style");
  s.id = "ap3d-css";
  s.textContent = `
  #ap3d{position:fixed;inset:0;z-index:999999;background:#000;overflow:hidden;font-family:Inter,'Segoe UI',system-ui,sans-serif;
    transition:opacity .6s cubic-bezier(.4,0,.2,1)}
  #ap3d canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
  #ap3d .vig{position:absolute;inset:0;pointer-events:none;background:radial-gradient(120% 90% at 60% 50%,transparent 45%,rgba(0,0,0,.75) 100%)}
  #ap3d .title{position:absolute;left:clamp(24px,6vw,96px);bottom:clamp(64px,13vh,150px);pointer-events:none;max-width:min(92vw,1100px)}
  #ap3d .ln{overflow:hidden;display:block}
  #ap3d .ln span{display:block;transform:translateY(105%);transition:transform .9s cubic-bezier(.16,1,.3,1)}
  #ap3d .shade{position:absolute;inset:0;pointer-events:none;background:linear-gradient(20deg,rgba(0,0,0,.92) 0%,rgba(0,0,0,.55) 34%,transparent 62%)}
  #ap3d .l1 span{font:400 clamp(20px,2.9vw,40px)/1.05 'Archivo Black','Arial Black',Inter,sans-serif;letter-spacing:.3em;color:#E6E6E6}
  #ap3d .l2 span{font:400 clamp(40px,7.4vw,118px)/.98 'Archivo Black','Arial Black',Inter,sans-serif;letter-spacing:-.005em;color:#fff;
    margin-top:.12em;text-shadow:0 2px 30px rgba(0,0,0,.6)}
  #ap3d .rule{height:2px;width:clamp(120px,18vw,260px);background:#fff;margin:22px 0 14px;transform:scaleX(0);transform-origin:left;
    transition:transform .8s cubic-bezier(.16,1,.3,1) .25s}
  #ap3d .sub{color:#B3B3B3;font-size:clamp(13px,1.2vw,17px);letter-spacing:.24em;text-transform:uppercase;opacity:0;transition:opacity .6s ease .45s}
  #ap3d.show-title .ln span{transform:none} #ap3d.show-title .l2 span{transition-delay:.12s}
  #ap3d.show-title .rule{transform:scaleX(1)} #ap3d.show-title .sub{opacity:1}
  #ap3d .skip{position:absolute;right:28px;bottom:26px;background:rgba(0,0,0,.4);color:#fff;border:1px solid #444;border-radius:6px;
    font:500 13px Inter,'Segoe UI',sans-serif;letter-spacing:.08em;text-transform:uppercase;padding:9px 16px;cursor:pointer;transition:background .15s,border-color .15s}
  #ap3d .skip:hover{background:#292929;border-color:#777} #ap3d .skip:focus-visible{outline:2px solid #fff;outline-offset:2px}
  #ap3d .prog{position:absolute;left:0;bottom:0;height:2px;background:#fff;opacity:.5;width:0}
  #ap3d .fb{position:absolute;left:0;right:0;top:38%;height:120px;display:flex;gap:12px;padding:0 12px;opacity:.5;
    animation:ap3d-fb 4.6s linear both}
  #ap3d .fb i{flex:0 0 150px;border:1px solid #444;border-radius:3px;background:linear-gradient(#181818,#0b0b0b)}
  @keyframes ap3d-fb{from{transform:translateX(10%)}to{transform:translateX(-40%)}}
  @media (prefers-reduced-motion: reduce){#ap3d .ln span,#ap3d .rule,#ap3d .sub{transition:none!important}}`;
  doc.head.appendChild(s);
  return s;
}

function overlay() {
  const el = doc.createElement("div");
  el.id = "ap3d";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "AI Promo Intelligence Studio introduction");
  el.innerHTML = '<div class="vig"></div><div class="shade"></div><div class="title"><div class="ln l1"><span>AI PROMO</span></div>' +
    '<div class="ln l2"><span>INTELLIGENCE STUDIO</span></div><div class="rule"></div>' +
    '<div class="sub">Editorial Intelligence for Microdrama</div></div>' +
    '<button class="skip" type="button">Skip intro</button><div class="prog"></div>';
  doc.body.appendChild(el);
  return el;
}

async function run() {
  const style = css();
  const el = overlay();
  let finished = false, raf = 0, cleanup = () => {};
  const finish = () => {
    if (finished) return; finished = true;
    try { local && local.setItem(KEY, String(Date.now())); } catch (e) {}
    el.style.opacity = "0";
    setTimeout(() => { cancelAnimationFrame(raf); try { cleanup(); } catch (e) {} el.remove(); style.remove();
      doc.removeEventListener("keydown", onKey); }, 650);
  };
  const onKey = (e) => { if (e.key === "Escape") finish(); };
  el.querySelector(".skip").addEventListener("click", finish);
  doc.addEventListener("keydown", onKey);
  if (FREEZE === null) setTimeout(finish, 9000);              // hard failsafe

  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const prog = el.querySelector(".prog");

  let THREE = null;
  try { THREE = await import("/app/static/vendor/three/three.module.js"); } catch (e) { THREE = null; }
  const canvas = doc.createElement("canvas");
  el.insertBefore(canvas, el.firstChild);
  let renderer = null;
  if (THREE) {
    try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" }); }
    catch (e) { renderer = null; }
  }
  if (!renderer) {                                            // CSS fallback: still black, still monochrome
    canvas.remove();
    const fb = doc.createElement("div"); fb.className = "fb";
    fb.innerHTML = "<i></i>".repeat(14);
    if (!still) el.insertBefore(fb, el.firstChild);
    requestAnimationFrame(() => el.classList.add("show-title"));
    setTimeout(finish, still ? 1600 : 4600);
    return;
  }

  const scene = buildScene(THREE, renderer, canvas);
  cleanup = scene.dispose;
  if (FREEZE !== null) { scene.update(FREEZE); if (FREEZE > 2.9) el.classList.add("show-title"); return; }
  if (!still) setTimeout(finish, (DURATION - 0.55) * 1000 + 60);   // ends on time even if frames are throttled
  const t0 = performance.now();
  const tick = () => {
    const t = still ? DURATION - 0.6 : (performance.now() - t0) / 1000;
    scene.update(t);
    prog.style.width = Math.min(100, (t / DURATION) * 100) + "%";
    if (t > 2.9 && !el.classList.contains("show-title")) el.classList.add("show-title");
    if (still) { setTimeout(finish, 1800); return; }          // one composed frame, no motion
    if (t >= DURATION - 0.55) { finish(); }
    if (!finished || t < DURATION + 0.7) raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
}

/* ------------------------------------------------------------------ scene */
function buildScene(THREE, renderer, canvas) {
  const W = () => window.innerWidth, H = () => window.innerHeight;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(W(), H(), false);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);
  scene.fog = new THREE.Fog(0x000000, 16, 42);
  const camera = new THREE.PerspectiveCamera(34, W() / H(), 0.1, 100);

  // ---- materials (monochrome only) ----
  const M = {
    silver: new THREE.MeshStandardMaterial({ color: 0xc8c8c8, metalness: 0.9, roughness: 0.32 }),
    brushed: new THREE.MeshStandardMaterial({ color: 0x8a8a8a, metalness: 0.8, roughness: 0.45 }),
    matte: new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.15, roughness: 0.7 }),
    film: new THREE.MeshStandardMaterial({ color: 0x161616, metalness: 0.3, roughness: 0.45, side: THREE.DoubleSide }),
    floor: new THREE.MeshStandardMaterial({ color: 0x060606, metalness: 0.4, roughness: 0.55 }),
    white: new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0.1, roughness: 0.4, emissive: 0x444444 }),
    line: new THREE.MeshStandardMaterial({ color: 0x5a5a5a, metalness: 0.6, roughness: 0.4 }),
  };
  const disposables = [];
  const keep = (x) => { disposables.push(x); return x; };

  // ---- lights (white only) ----
  const amb = new THREE.AmbientLight(0xffffff, 0.06); scene.add(amb);
  const key = new THREE.SpotLight(0xffffff, 0, 0, Math.PI / 6.5, 0.55, 0);
  key.position.set(-1.5, 9, 9); key.castShadow = true; key.shadow.mapSize.set(1024, 1024); key.shadow.bias = -0.0004;
  scene.add(key); scene.add(key.target);
  const rim = new THREE.DirectionalLight(0xffffff, 0); rim.position.set(6, 4, -8); scene.add(rim);
  const fill = new THREE.PointLight(0xffffff, 0, 30, 0); fill.position.set(-8, 1, 6); scene.add(fill);

  // ---- floor ----
  const floor = new THREE.Mesh(keep(new THREE.PlaneGeometry(80, 80)), M.floor);
  floor.rotation.x = -Math.PI / 2; floor.position.y = -2.7; floor.receiveShadow = true; scene.add(floor);

  // ---- film reel ----
  const reel = new THREE.Group();
  const flangeShape = new THREE.Shape();
  flangeShape.absarc(0, 0, 2.3, 0, Math.PI * 2, false);
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2 + Math.PI / 6, h = new THREE.Path();
    h.absarc(Math.cos(a) * 1.28, Math.sin(a) * 1.28, 0.5, 0, Math.PI * 2, true); flangeShape.holes.push(h);
  }
  const hub = new THREE.Path(); hub.absarc(0, 0, 0.2, 0, Math.PI * 2, true); flangeShape.holes.push(hub);
  const flangeGeo = keep(new THREE.ExtrudeGeometry(flangeShape, { depth: 0.07, bevelEnabled: true, bevelThickness: 0.02,
    bevelSize: 0.02, bevelSegments: 2, curveSegments: 72 }));
  flangeGeo.center();
  for (const z of [-0.47, 0.47]) {
    const f = new THREE.Mesh(flangeGeo, M.silver); f.position.z = z; f.castShadow = true; f.receiveShadow = true; reel.add(f);
  }
  const coil = new THREE.Mesh(keep(new THREE.CylinderGeometry(1.62, 1.62, 0.86, 96, 1, false)), M.matte);
  coil.rotation.x = Math.PI / 2; coil.castShadow = true; reel.add(coil);
  for (let i = 1; i <= 5; i++) {               // wound layers read as fine rings on the coil face
    const ring = new THREE.Mesh(keep(new THREE.TorusGeometry(0.45 + i * 0.22, 0.006, 6, 96)), M.line);
    ring.position.z = 0.431; reel.add(ring);
    const ring2 = ring.clone(); ring2.position.z = -0.431; reel.add(ring2);
  }
  const hubM = new THREE.Mesh(keep(new THREE.CylinderGeometry(0.34, 0.34, 1.12, 48)), M.brushed);
  hubM.rotation.x = Math.PI / 2; reel.add(hubM);
  reel.position.set(2.7, 0.55, 0); reel.rotation.y = -0.55; scene.add(reel);

  // ---- film strip along a curve ----
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(3.15, 2.25, -0.35), new THREE.Vector3(4.6, 2.55, 0.5), new THREE.Vector3(6.4, 1.5, 1.5),
    new THREE.Vector3(7.5, -0.3, 1.1), new THREE.Vector3(9.0, -1.6, -0.6), new THREE.Vector3(11.5, -2.0, -2.6)]);
  const FW = 0.86, FH = 0.66;
  const frameShape = new THREE.Shape();
  frameShape.moveTo(-FW / 2, -FH / 2); frameShape.lineTo(FW / 2, -FH / 2); frameShape.lineTo(FW / 2, FH / 2); frameShape.lineTo(-FW / 2, FH / 2);
  for (let i = 0; i < 4; i++) {
    for (const y of [FH / 2 - 0.085, -FH / 2 + 0.045]) {
      const x = -FW / 2 + 0.09 + i * 0.22, h = new THREE.Path();
      h.moveTo(x, y); h.lineTo(x + 0.08, y); h.lineTo(x + 0.08, y + 0.04); h.lineTo(x, y + 0.04); frameShape.holes.push(h);
    }
  }
  const frameGeo = keep(new THREE.ExtrudeGeometry(frameShape, { depth: 0.018, bevelEnabled: false }));
  frameGeo.translate(0, 0, -0.009);
  const picGeo = keep(new THREE.PlaneGeometry(FW * 0.78, FH * 0.56));
  const N = 24, frames = [];
  const shades = [0x2a2a2a, 0x3c3c3c, 0x333333, 0x4a4a4a, 0x2f2f2f, 0x404040];
  for (let i = 0; i < N; i++) {
    const g = new THREE.Group();
    const fr = new THREE.Mesh(frameGeo, M.film); fr.castShadow = true; g.add(fr);
    const picMat = keep(new THREE.MeshStandardMaterial({ color: shades[i % shades.length], metalness: 0.2, roughness: 0.5,
      emissive: 0x000000, side: THREE.DoubleSide }));
    const pic = new THREE.Mesh(picGeo, picMat); pic.position.z = 0.011; g.add(pic);
    const back = pic.clone(); back.position.z = -0.011; back.rotation.y = Math.PI; g.add(back);
    g.userData = { pic: picMat, picked: i === 9 || i === 11 || i === 13 };
    scene.add(g); frames.push(g);
  }
  const X = new THREE.Vector3(), Y = new THREE.Vector3(), Z = new THREE.Vector3(), UP = new THREE.Vector3(0, 0, 1), mtx = new THREE.Matrix4();
  function placeFrames(offset, pickAmt) {
    const span = 0.96 / N;
    for (let i = 0; i < N; i++) {
      let u = (i * span + offset) % 0.96; if (u < 0) u += 0.96;
      const p = curve.getPointAt(u), tan = curve.getTangentAt(u);
      X.copy(tan).normalize();
      Z.copy(UP).addScaledVector(X, -X.dot(UP)).normalize();
      Y.crossVectors(Z, X).normalize();
      mtx.makeBasis(X, Y, Z);
      const g = frames[i]; g.position.copy(p); g.quaternion.setFromRotationMatrix(mtx);
      const hl = g.userData.picked ? pickAmt : 0;
      g.userData.pic.color.setScalar(0.17 + hl * 0.83);
      g.userData.pic.emissive.setScalar(hl * 0.35);
      g.position.addScaledVector(Z, hl * 0.25);
    }
  }

  // ---- screenplay pages (generic layout, no real script text) ----
  function pageTexture(seed) {
    const c = document.createElement("canvas"); c.width = 512; c.height = 660;
    const x = c.getContext("2d");
    x.fillStyle = "#ececec"; x.fillRect(0, 0, 512, 660);
    x.fillStyle = "#1a1a1a"; x.font = "bold 22px Courier New, monospace"; x.fillText("SCENE " + String(seed + 1).padStart(2, "0"), 48, 70);
    let y = 112, r = seed * 7 + 3;
    const rnd = () => { r = (r * 9301 + 49297) % 233280; return r / 233280; };
    for (let i = 0; i < 18; i++) {
      const dialogue = i % 4 === 1 || i % 4 === 2;
      x.fillStyle = dialogue ? "#4a4a4a" : "#8c8c8c";
      const indent = dialogue ? 150 : 48, w = dialogue ? 200 + rnd() * 100 : 260 + rnd() * 160;
      x.fillRect(indent, y, w, 8); y += i % 4 === 3 ? 34 : 22;
    }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return keep(t);
  }
  const pageGeo = keep(new THREE.BoxGeometry(1.55, 2.0, 0.012));
  const pages = [];
  const pageSpots = [
    { from: [-1.0, -5, -1.0], to: [-1.2, 1.25, -1.6], rot: [-0.08, 0.42, 0.06], end: [-1.5, 1.05, -2.0] },
    { from: [0.4, -6, -2.6], to: [0.3, 2.0, -3.0], rot: [-0.04, 0.3, -0.05], end: [-0.2, 1.6, -2.8] },
    { from: [-2.6, -5, -2.8], to: [-2.9, 0.9, -3.3], rot: [0.02, 0.55, 0.1], end: [-2.9, 0.75, -3.1] }];
  pageSpots.forEach((s, i) => {
    const mat = keep(new THREE.MeshStandardMaterial({ map: pageTexture(i), roughness: 0.92, metalness: 0.0 }));
    const edge = keep(new THREE.MeshStandardMaterial({ color: 0xdcdcdc, roughness: 0.9 }));
    const m = new THREE.Mesh(pageGeo, [edge, edge, edge, edge, mat, edge]);
    m.castShadow = true; m.receiveShadow = true; m.userData = s; scene.add(m); pages.push(m);
  });

  // ---- editorial timeline ----
  const tl = new THREE.Group();
  const bar = new THREE.Mesh(keep(new THREE.BoxGeometry(11, 0.035, 0.035)), M.brushed); tl.add(bar);
  const tickGeo = keep(new THREE.BoxGeometry(0.012, 0.16, 0.012));
  for (let i = 0; i <= 44; i++) { const k = new THREE.Mesh(tickGeo, M.line); k.position.set(-5.5 + i * 0.25, i % 4 ? 0.06 : 0.11, 0); tl.add(k); }
  const clipGeo = keep(new THREE.BoxGeometry(1, 0.2, 0.2));
  const clips = [[-2.6, 0.9], [0.4, 0.6], [2.9, 1.1]].map(([x, w]) => {
    const c = new THREE.Mesh(clipGeo, M.white); c.position.set(x, 0.24, 0); c.scale.set(w, 1, 1); c.castShadow = true; tl.add(c); return c;
  });
  tl.position.set(0.2, -2.2, 2.4); tl.rotation.y = -0.12; scene.add(tl);

  // ---- motion ----
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const ease = (v) => 1 - Math.pow(1 - clamp01(v), 3);
  const easeIO = (v) => { v = clamp01(v); return v * v * (3 - 2 * v); };
  const lerp = (a, b, k) => a + (b - a) * k;
  const camFrom = new THREE.Vector3(0.6, 1.9, 22), camMid = new THREE.Vector3(1.4, 1.25, 15.5), camEnd = new THREE.Vector3(2.0, 0.95, 13.6);
  const lookFrom = new THREE.Vector3(2.4, 0.6, 0), lookEnd = new THREE.Vector3(2.0, -0.1, 0);
  let fit = 1;                                   // narrow screens: pull the camera back so nothing crowds the title
  const look = new THREE.Vector3();

  function update(t) {
    // 0-1 s: light reveals the reel
    key.intensity = 5.2 * ease(t / 1.0);
    rim.intensity = 2.0 * ease((t - 0.3) / 1.2);
    fill.intensity = 0.55 * ease((t - 0.5) / 1.5);
    key.target.position.set(2.6, 0.2, 0);
    // reel turns (accelerates 1-2 s, settles after 4 s)
    const spin = t < 1 ? t * 0.15 : 0.15 + (t - 1) * 0.9 - Math.max(0, t - 4) * 0.45;
    reel.rotation.z = -spin * 1.6;
    // film strip flows; three frames picked out 2-3.2 s
    placeFrames(0.02 + t * 0.045, ease((t - 2.0) / 0.9));
    // screenplay pages rise 1.9-3.1 s, then settle 4-5 s
    pages.forEach((p, i) => {
      const s = p.userData, k = ease((t - 1.9 - i * 0.15) / 1.1), e = easeIO((t - 4.0) / 0.9);
      const tx = lerp(s.to[0], s.end[0], e), ty = lerp(s.to[1], s.end[1], e), tz = lerp(s.to[2], s.end[2], e);
      p.position.set(lerp(s.from[0], tx, k), lerp(s.from[1], ty, k) + Math.sin(t * 1.4 + i) * 0.03 * (1 - e), lerp(s.from[2], tz, k));
      p.rotation.set(s.rot[0] + (1 - k) * 0.9, s.rot[1], s.rot[2] + (1 - k) * 0.3);
    });
    // timeline draws in 2.2-3.2 s, clips drop in 3-3.8 s
    tl.scale.x = Math.max(0.0001, ease((t - 2.2) / 1.0));
    clips.forEach((c, i) => { const k = ease((t - 3.0 - i * 0.12) / 0.6); c.position.y = lerp(1.4, 0.24, k); c.visible = k > 0.01; });
    // camera dolly 0-4.6 s
    const a = easeIO(t / 2.6), b = easeIO((t - 2.4) / 2.2);
    camera.position.copy(camFrom).lerp(camMid, a).lerp(camEnd, b);
    camera.position.z *= fit;
    camera.position.y += Math.sin(t * 0.8) * 0.04;
    look.copy(lookFrom).lerp(lookEnd, b);
    camera.lookAt(look);
    renderer.render(scene, camera);
  }

  const onResize = () => { camera.aspect = W() / H(); fit = Math.max(1, 1.65 / camera.aspect);
    camera.updateProjectionMatrix(); renderer.setSize(W(), H(), false); };
  window.addEventListener("resize", onResize);
  onResize();

  function dispose() {
    window.removeEventListener("resize", onResize);
    disposables.forEach((d) => d.dispose && d.dispose());
    Object.values(M).forEach((m) => m.dispose());
    renderer.dispose();
    try { renderer.forceContextLoss(); } catch (e) {}
  }
  return { update, dispose };
}
