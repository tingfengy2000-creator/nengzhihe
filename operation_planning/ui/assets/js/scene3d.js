/* 能见度 · 首屏 3D 微缩场景（three.js r128，离线 vendored）
 *
 * 由真实逐小时数据驱动（典型周 168 小时）：
 *   - 太阳光强随当时光伏发电（太阳轨迹为 6–18 点的示意，不是天文计算）；
 *   - 窗户在空调用电时亮起；风机转速随风机发电；
 *   - 能量粒子：青色飞进房间 = 当时用上，橙色飘走 = 浪费；粒子数量与该小时数值成比例（仅用于显示）。
 * HUD 显示当前日期时刻和这一小时的用电 / 光伏 / 风机 / 用上 / 浪费原始数值。
 * WebGL 不可用时显示静态 SVG 插画，HUD 照常按数据播放；减少动态效果时只显示一帧。
 * 轻量：低多边形、阴影贴图 2048、像素比上限 2；离开视野或页面隐藏时暂停。
 */
import { $, fmt, reduceMotion } from './util.js';
import { WEEKDAYS } from './data.js';

const HOURS_PER_SEC = 2.6;

function fallbackSvg() {
  return `<svg class="scene-fallback-svg" viewBox="0 0 400 340" role="img" aria-label="静态插画：办公楼、屋顶光伏和一台小风机">
    <ellipse cx="200" cy="290" rx="180" ry="38" fill="var(--bg-2)"/>
    <rect x="80" y="150" width="190" height="130" rx="4" fill="var(--surface)" stroke="var(--line-strong)"/>
    <rect x="270" y="210" width="70" height="70" rx="3" fill="var(--surface)" stroke="var(--line-strong)"/>
    <rect x="74" y="143" width="202" height="9" rx="2" fill="var(--ink-2)"/>
    ${[0, 1, 2, 3, 4].map((c) => [0, 1].map((r) => `<rect class="fb-win" x="${96 + c * 34}" y="${170 + r * 46}" width="24" height="24" rx="2" fill="var(--ink-3)" fill-opacity=".35"/>`).join('')).join('')}
    ${[0, 1, 2, 3].map((c) => `<path class="fb-pv" d="M${92 + c * 44} 136 l10 -24 h30 l-10 24z" fill="#24385A" stroke="var(--c-pv)" stroke-width="1.2"/>`).join('')}
    <line x1="350" y1="282" x2="350" y2="90" stroke="var(--ink-3)" stroke-width="4" stroke-linecap="round"/>
    <g class="fb-rotor" transform="translate(350 90)"><circle r="5" fill="var(--ink-2)"/>
      <path d="M0 0 L-4 -58 L4 -58Z M0 0 L52 26 L48 33Z M0 0 L-48 33 L-52 26Z" fill="var(--ink-2)" fill-opacity=".85"/></g>
    <circle class="fb-sun" cx="60" cy="60" r="20" fill="var(--c-pv)" fill-opacity=".85"/>
  </svg>`;
}

export function createScene(stageEl, hud) {
  let W = null, n = 0, maxLoad = 1, maxGen = 1, hour = 8, last = performance.now(), running = false, raf = null, visible = true;
  let three = null; // { renderer, scene, cam, ... }
  const canvas = $('canvas', stageEl), fb = $('[data-scene-fallback]', stageEl);

  function at(arr, h) { const i = Math.floor(h) % n, j = (i + 1) % n, t = h - Math.floor(h); return (arr[i] || 0) + ((arr[j] || 0) - (arr[i] || 0)) * t; }

  function updateHud(h) {
    if (!W) return;
    const i = Math.floor(h) % n, t = W.ts[i] || '';
    const d = new Date(t.slice(0, 10) + 'T12:00:00');
    hud.date.textContent = `${t.slice(0, 10)} ${WEEKDAYS[d.getDay()] || ''} ${t.slice(11, 16)}`;
    hud.load.textContent = fmt.fixed(W.load[i], 2);
    hud.pv.textContent = fmt.fixed(W.pv[i], 2);
    hud.wind.textContent = fmt.fixed(W.wind[i], 2);
    hud.self.textContent = fmt.fixed(W.self[i], 2);
    hud.waste.textContent = fmt.fixed(W.curt[i], 2);
    hud.bar.style.width = ((h / n) * 100).toFixed(1) + '%';
  }

  function initThree() {
    const THREE = window.THREE;
    if (!THREE) return null;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      if (!renderer.getContext()) return null;
    } catch (e) { return null; }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputEncoding = THREE.sRGBEncoding; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.1;
    const scene = new THREE.Scene();
    const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
    const size = () => {
      const w = canvas.clientWidth || stageEl.clientWidth || 600, h = canvas.clientHeight || stageEl.clientHeight || 500, asp = w / h, f = Math.max(8.6, 11.8 / asp);
      cam.left = -f * asp; cam.right = f * asp; cam.top = f; cam.bottom = -f; cam.updateProjectionMatrix(); renderer.setSize(w, h, false);
    };
    size();
    const L = (c) => new THREE.Color(c).convertSRGBToLinear();
    const M = (c, o) => new THREE.MeshStandardMaterial(Object.assign({ color: L(c), roughness: 0.85, metalness: 0 }, o || {}));
    const mesh = (g, m, x, y, z, cast, rec) => { const o = new THREE.Mesh(g, m); o.position.set(x || 0, y || 0, z || 0); o.castShadow = cast !== false; o.receiveShadow = rec !== false; scene.add(o); return o; };
    // 底座与步道
    mesh(new THREE.CylinderGeometry(9.2, 9.5, 0.8, 72), M('#9FB8AB'), 0, -0.4, 0, false, true);
    mesh(new THREE.CylinderGeometry(9.2, 9.2, 0.02, 72), M('#C3DCCB'), 0, 0.01, 0, false, true);
    mesh(new THREE.BoxGeometry(2.2, 0.03, 7.5), M('#F3F1EC'), -0.6, 0.03, 4.6, false, true);
    // 主楼与附楼
    const wall = M('#F3EFE7');
    mesh(new THREE.BoxGeometry(5.6, 3.4, 3.6), wall, -0.6, 1.7, 0);
    mesh(new THREE.BoxGeometry(5.9, 0.18, 3.9), M('#2F4A50'), -0.6, 3.49, 0);
    mesh(new THREE.BoxGeometry(2.4, 1.9, 2.6), wall, 3.0, 0.95, 0.5);
    mesh(new THREE.BoxGeometry(2.6, 0.14, 2.8), M('#2F4A50'), 3.0, 1.97, 0.5);
    mesh(new THREE.BoxGeometry(1.8, 0.12, 0.9), M('#DDE3E1'), -0.6, 1.2, 2.2);
    // 窗户（空调用电时亮起）
    const winMats = [];
    const win = (x, y, z, ry) => { const m = new THREE.MeshStandardMaterial({ color: L('#1E2E35'), roughness: 0.2, metalness: 0.3, emissive: L('#FFC872'), emissiveIntensity: 0 }); winMats.push(m); const o = mesh(new THREE.PlaneGeometry(0.78, 0.72), m, x, y, z, false, false); o.rotation.y = ry || 0; };
    for (let r = 0; r < 2; r++) for (let c = 0; c < 5; c++) if (!(r === 0 && c === 2)) win(-2.8 + c * 1.1, 1.15 + r * 1.25, 1.81);
    for (let r = 0; r < 2; r++) for (let c = 0; c < 3; c++) win(2.21, 1.15 + r * 1.25, -1.15 + c * 1.15, Math.PI / 2);
    mesh(new THREE.PlaneGeometry(0.9, 1.15), M('#3B4A50', { roughness: 0.3 }), -0.6, 0.58, 1.81, false, false);
    [0.72, 1.97].forEach((y) => mesh(new THREE.BoxGeometry(5.62, 0.08, 0.02), M('#D9D2C5'), -0.6, y, 1.805, false, false));
    mesh(new THREE.BoxGeometry(5.62, 0.35, 0.02), M('#2F4A50'), -0.6, 3.18, 1.805, false, false);
    // 空调外机
    const fans = [];
    for (let k = 0; k < 3; k++) {
      mesh(new THREE.BoxGeometry(0.62, 0.46, 0.3), M('#EEF1F0'), -3.75, 0.55 + k * 1.05, -0.6);
      const f = new THREE.Mesh(new THREE.CircleGeometry(0.15, 20), M('#9AA6A3')); f.position.set(-4.065, 0.55 + k * 1.05, -0.6); f.rotation.y = -Math.PI / 2; scene.add(f); fans.push(f);
    }
    // 屋顶光伏
    const pvMats = [];
    for (let pr = 0; pr < 2; pr++) for (let pc = 0; pc < 4; pc++) {
      const pm = new THREE.MeshStandardMaterial({ color: L('#24385A'), roughness: 0.28, metalness: 0.55, emissive: L('#FFB547'), emissiveIntensity: 0 }); pvMats.push(pm);
      const p = mesh(new THREE.BoxGeometry(1.15, 0.06, 0.82), pm, -2.55 + pc * 1.3, 3.85, -0.75 + pr * 1.25); p.rotation.x = -0.42;
      mesh(new THREE.BoxGeometry(0.06, 0.36, 0.06), M('#B9C3C0'), -2.55 + pc * 1.3, 3.68, -0.45 + pr * 1.25);
    }
    // 小风机
    const tx = 5.3, tz = -3.2;
    const turbine = new THREE.Group(); scene.add(turbine);
    const tower = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.18, 6.6, 20), M('#F4F6F5', { roughness: 0.5 })); tower.position.set(tx, 3.3, tz); tower.castShadow = true; turbine.add(tower);
    const nac = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.36, 0.36), M('#EEF1F0', { roughness: 0.45 })); nac.position.set(tx, 6.66, tz); nac.castShadow = true; turbine.add(nac);
    const hub = new THREE.Group(); hub.position.set(tx, 6.66, tz + 0.28); turbine.add(hub);
    const blade = M('#FFFFFF', { roughness: 0.4 });
    for (let b = 0; b < 3; b++) { const bl = new THREE.Mesh(new THREE.BoxGeometry(0.16, 2.6, 0.04), blade); bl.geometry.translate(0, 1.3, 0); bl.rotation.z = (b * Math.PI * 2) / 3; bl.castShadow = true; hub.add(bl); }
    hub.add(new THREE.Mesh(new THREE.SphereGeometry(0.14, 12, 10), M('#DDE3E1')));
    // 树
    const leaf = M('#7FB59A', { flatShading: true }), leaf2 = M('#5E9E83', { flatShading: true }), trunk = M('#9C8B78');
    [[-6.6, 2.4, 1], [-5.8, 4.4, 0.8], [-7.0, -1.6, 1.1], [1.6, 5.8, 0.75], [6.9, 1.8, 0.9], [-3.4, -5.6, 0.95], [2.6, -5.4, 0.8]].forEach((t, i) => {
      mesh(new THREE.CylinderGeometry(0.07, 0.1, 0.6, 8), trunk, t[0], 0.3, t[1]);
      mesh(new THREE.IcosahedronGeometry(0.62 * t[2], 0), i % 2 ? leaf : leaf2, t[0], 0.95 * t[2] + 0.35, t[1]);
    });
    // 灯光
    const hemi = new THREE.HemisphereLight('#EAF4FF', '#8FA59A', 0.55); scene.add(hemi);
    const sun = new THREE.DirectionalLight('#FFFFFF', 1.6); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: 1, far: 60 }); sun.shadow.bias = -0.0006;
    scene.add(sun); scene.add(sun.target);
    const fill = new THREE.DirectionalLight('#9FC2FF', 0.15); fill.position.set(-10, 8, 6); scene.add(fill);
    // 粒子
    const parts = [], pg = new THREE.SphereGeometry(0.07, 8, 6);
    const pvSrc = new THREE.Vector3(-0.6, 4.1, 0), wSrc = new THREE.Vector3(tx, 6.66, tz);
    const spawn = (kind, src) => {
      const m = new THREE.MeshBasicMaterial({ color: kind === 'self' ? '#16A394' : '#E0802A', transparent: true, opacity: 1 });
      const o = new THREE.Mesh(pg, m); scene.add(o);
      const a = src.clone();
      const end = kind === 'self' ? new THREE.Vector3(-2.8 + Math.random() * 4.4, 1.2 + Math.random() * 1.3, 1.9) : new THREE.Vector3(src.x + (Math.random() - 0.5) * 5, 9.5 + Math.random() * 2, src.z + (Math.random() - 0.5) * 4);
      const mid = a.clone().lerp(end, 0.5); mid.y += kind === 'self' ? 1.6 : 1.0;
      parts.push({ o, a, b: mid, c: end, t: 0, kind, spd: 0.5 + Math.random() * 0.3 });
    };
    cam.position.set(16, 13.5, 17); cam.lookAt(0.4, 1.9, 0);
    const base = cam.position.clone();
    return { THREE, renderer, scene, cam, size, base, winMats, pvMats, fans, hub, turbine, hemi, sun, parts, spawn, pvSrc, wSrc, acc: { self: 0, waste: 0 }, rot: 0 };
  }

  function setSky(elev) {
    const sky = stageEl.closest('.hero') && stageEl.closest('.hero').querySelector('.sky');
    if (!sky) return;
    const dark = document.documentElement.getAttribute('data-theme') === 'dark' || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    const day = dark ? '#1D3A44' : '#FFE7B8', night = dark ? '#0E1C2C' : '#D5E0EF', edge = dark ? '#0C1110' : '#FBFBFA';
    sky.style.background = `radial-gradient(58% 70% at 74% 46%, ${elev > 0.05 ? day : night} 0%, ${edge} 70%)`;
  }

  function renderFrame(now, dt) {
    const s = three;
    const hd = hour % 24, load = at(W.load, hour), pv = at(W.pv, hour), wind = at(W.wind, hour), self = at(W.self, hour), waste = at(W.curt, hour);
    const sp = (hd - 6) / 12, elev = Math.sin(Math.PI * Math.max(0, Math.min(1, sp)));
    setSky(sp > 0 && sp < 1 ? elev : 0);
    if (!s) return;
    const pvN = pv / maxGen, loadN = load / maxLoad, windN = wind / maxGen;
    const az = -1.25 + 2.5 * Math.max(0, Math.min(1, sp));
    s.sun.position.set(Math.sin(az) * 14, Math.max(0.5, elev * 16), Math.cos(az) * 10 + 4);
    s.sun.intensity = sp > 0 && sp < 1 ? 0.35 + 1.5 * Math.min(1, pvN + elev * 0.3) : 0;
    s.sun.color.set(elev < 0.35 ? '#FFC08A' : '#FFF6EA');
    s.hemi.intensity = 0.18 + 0.42 * elev; s.hemi.color.set(elev > 0 ? '#EAF4FF' : '#5E7398');
    s.renderer.toneMappingExposure = 0.62 + 0.3 * elev;
    s.winMats.forEach((m) => { m.emissiveIntensity = load > 1e-6 ? Math.min(1.6, 0.6 + loadN * 1.0) : 0; });
    s.pvMats.forEach((m) => { m.emissiveIntensity = Math.min(0.55, pvN * 0.55); });
    s.rot += dt * (wind > 1e-6 ? 1.2 + windN * 9 : 0.15); s.hub.rotation.z = -s.rot;
    s.fans.forEach((f) => { f.rotation.z += load > 1e-6 ? dt * 14 : 0; });
    if (!reduceMotion()) {
      // 粒子数量与该小时“用上/浪费”成比例（以本周最大发电量归一，仅用于显示）
      s.acc.self += (self / maxGen) * dt * HOURS_PER_SEC * 6; s.acc.waste += (waste / maxGen) * dt * HOURS_PER_SEC * 6;
      while (s.acc.self >= 1) { s.acc.self -= 1; s.spawn('self', pv >= wind ? s.pvSrc : s.wSrc); }
      while (s.acc.waste >= 1) { s.acc.waste -= 1; s.spawn('waste', Math.random() < pv / (pv + wind + 1e-9) ? s.pvSrc : s.wSrc); }
    }
    for (let i = s.parts.length - 1; i >= 0; i--) {
      const q = s.parts[i]; q.t += dt * q.spd; const t = q.t, u = 1 - t;
      q.o.position.set(u * u * q.a.x + 2 * u * t * q.b.x + t * t * q.c.x, u * u * q.a.y + 2 * u * t * q.b.y + t * t * q.c.y, u * u * q.a.z + 2 * u * t * q.b.z + t * t * q.c.z);
      q.o.material.opacity = q.kind === 'waste' ? Math.max(0, 1 - t) : Math.min(1, 1.4 - t);
      if (t >= 1) { s.scene.remove(q.o); q.o.material.dispose(); s.parts.splice(i, 1); }
    }
    const sw = reduceMotion() ? 0 : Math.sin(now / 9000) * 0.09;
    s.cam.position.set(s.base.x * Math.cos(sw) - s.base.z * Math.sin(sw), s.base.y, s.base.x * Math.sin(sw) + s.base.z * Math.cos(sw)); s.cam.lookAt(0.4, 1.9, 0);
    s.renderer.render(s.scene, s.cam);
  }

  function updateFallback() {
    if (!fb || fb.hidden) return;
    const i = Math.floor(hour) % n;
    const pvN = (W.pv[i] || 0) / maxGen, loadN = (W.load[i] || 0) / maxLoad;
    fb.querySelectorAll('.fb-win').forEach((w) => { w.setAttribute('fill', loadN > 0 ? '#FFC872' : 'var(--ink-3)'); w.setAttribute('fill-opacity', loadN > 0 ? String(0.45 + loadN * 0.5) : '.35'); });
    fb.querySelectorAll('.fb-pv').forEach((p) => p.setAttribute('fill', pvN > 0.05 ? '#3A557F' : '#24385A'));
    const sun = fb.querySelector('.fb-sun'); if (sun) sun.setAttribute('fill-opacity', String(0.15 + pvN * 0.85));
  }

  let hudTick = 0;
  function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!reduceMotion()) hour = (hour + dt * HOURS_PER_SEC) % n;
    renderFrame(now, dt);
    if (now - hudTick > 120) { hudTick = now; updateHud(hour); updateFallback(); }
    if (running && !reduceMotion()) raf = requestAnimationFrame(loop);
  }
  function start() {
    if (!W || running) return;
    running = true; last = performance.now();
    raf = requestAnimationFrame(loop);
  }
  function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = null; }

  const io = 'IntersectionObserver' in window ? new IntersectionObserver((es) => { es.forEach((e) => { visible = e.isIntersecting; if (visible && !document.hidden) start(); else stop(); }); }, { threshold: 0.05 }) : null;
  if (io) io.observe(stageEl);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else if (visible) start(); });
  let rz = null;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (three) { three.size(); if (!running) renderFrame(performance.now(), 0); } }, 120); });

  return {
    /** week: { ts, load, pv, wind, self, curt }；windCount：0 时隐藏风机 */
    set(week, { windCount = 1 } = {}) {
      W = week; n = week.ts.length;
      maxLoad = Math.max(1e-9, ...week.load.map((v) => v || 0));
      maxGen = Math.max(1e-9, ...week.pv.map((v, i) => (v || 0) + (week.wind[i] || 0)));
      if (!three && !fb.dataset.on) {
        three = initThree();
        if (!three) { fb.hidden = false; fb.dataset.on = '1'; fb.innerHTML = fallbackSvg() + '<p class="scene-fallback-note">当前浏览器无法显示三维场景，已改用静态插画；下方数值照常按逐小时数据播放。</p>'; canvas.hidden = true; }
      }
      if (three) three.turbine.visible = windCount > 0;
      // 默认从第一天 8 点开始；减少动态效果时停在第一天 12 点
      hour = reduceMotion() ? Math.min(12, n - 1) : Math.min(8, n - 1);
      updateHud(hour); updateFallback();
      if (reduceMotion()) { renderFrame(performance.now(), 0); return; }
      stop(); if (visible) start();
    },
    usesWebGL: () => !!three,
    stop
  };
}
