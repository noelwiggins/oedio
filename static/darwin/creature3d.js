/* Realistic 3D view of one tidal-pool creature, grown from its actual body plan.
   Every lobe of the body is one of its cells, in the place its genes put it; the cell types decide the
   material (chlorophyll-green photo cells, a muscular mouth, glossy eyes, beating flagella, chitin armour…).
   Colour, texture and thickness are an artist's interpretation: the simulation itself is 2D and has no skin. */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { MarchingCubes } from 'three/addons/objects/MarchingCubes.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const TINT = {
  0: [0.62, 0.52, 0.40], 1: [0.13, 0.42, 0.10], 2: [0.55, 0.12, 0.10], 3: [0.70, 0.66, 0.58], 4: [0.20, 0.16, 0.18],
  5: [0.32, 0.27, 0.20], 6: [0.80, 0.52, 0.14], 7: [0.40, 0.26, 0.62], 8: [0.80, 0.36, 0.48],
};
let active = null;

export function open(info) {
  if (active) active.close();
  const wrap = document.createElement('div'); wrap.className = 'c3d';
  wrap.innerHTML = `<div class="stage"><canvas></canvas>
    <div class="note">RENDERED FROM ITS BODY PLAN · DRAG TO TURN · SCROLL TO ZOOM</div>
    <div class="cap"><b><i></i></b><br><span class="c1"></span><br><span class="c2" style="opacity:.75"></span></div>
    <button class="close" aria-label="Close">×</button></div>`;
  document.body.appendChild(wrap);
  wrap.querySelector('i').textContent = info.name || 'unnamed lineage';
  wrap.querySelector('.c1').textContent = `${info.cells.length} cells: ` + Object.entries(info.counts || {}).map(([k, v]) => `${v} ${k}`).join(', ');
  wrap.querySelector('.c2').textContent = 'Every lobe is one of its cells, where its genes put it. Colours and textures are an interpretation; the simulation has no skin.';
  const canvas = wrap.querySelector('canvas');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.9;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  const water = new THREE.Color(0x0b3d48);
  scene.background = water; scene.fog = new THREE.FogExp2(water, 0.04);
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 200);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true; controls.autoRotate = true; controls.autoRotateSpeed = 0.6;
  controls.minDistance = 2; controls.maxDistance = 30;

  // light: sun from the surface, cool fill from below, a warm rim
  scene.add(new THREE.HemisphereLight(0x9fe8f0, 0x0a2028, 0.55));
  const sun = new THREE.DirectionalLight(0xfff1d6, 2.2); sun.position.set(3, 10, 4); sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024); sun.shadow.camera.left = sun.shadow.camera.bottom = -8; sun.shadow.camera.right = sun.shadow.camera.top = 8;
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0xffc89a, 0.7); rim.position.set(-6, 2, -5); scene.add(rim);

  // sea floor with moving caustics
  const caus = causticsTexture();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(80, 80, 1, 1),
    new THREE.MeshStandardMaterial({ color: 0x8a7a58, roughness: 0.95, map: sandTexture(), envMapIntensity: 0.4 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -3.2; floor.receiveShadow = true; scene.add(floor);
  const causMesh = new THREE.Group();
  [caus.texture, caus.texture2].forEach((tx, k) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(80, 80),
      new THREE.MeshBasicMaterial({ map: tx, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.12, fog: true }));
    m.rotation.x = -Math.PI / 2; m.position.y = 0.01 * k; causMesh.add(m);
  });
  causMesh.position.y = -3.18; scene.add(causMesh);
  // shafts of light and drifting marine snow
  const shafts = new THREE.Group();
  for (let i = 0; i < 7; i++) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 1.6, 22, 16, 1, true),
      new THREE.MeshBasicMaterial({ color: 0xcff6ff, transparent: true, opacity: 0.02, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    m.position.set((Math.random() - 0.5) * 16, 6, (Math.random() - 0.5) * 10 - 3); m.rotation.z = 0.25 + Math.random() * 0.1; shafts.add(m);
  }
  scene.add(shafts);
  const snowN = 900, sp = new Float32Array(snowN * 3);
  for (let i = 0; i < snowN; i++) { sp[i * 3] = (Math.random() - 0.5) * 30; sp[i * 3 + 1] = Math.random() * 14 - 3; sp[i * 3 + 2] = (Math.random() - 0.5) * 30; }
  const snowG = new THREE.BufferGeometry(); snowG.setAttribute('position', new THREE.BufferAttribute(sp, 3));
  const snow = new THREE.Points(snowG, new THREE.PointsMaterial({ color: 0xdff6f2, size: 0.035, transparent: true, opacity: 0.7, depthWrite: false }));
  scene.add(snow);

  // ── the creature ──────────────────────────────────────────────────
  const cells = info.cells, n = cells.length;
  const xs = cells.map(c => c[0]), ys = cells.map(c => c[1]);
  const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) + 1;
  const occ = new Set(cells.map(c => c[0] + ',' + c[1]));
  const neighbours = (x, y) => [[1, 0], [-1, 0], [0, 1], [0, -1]].filter(([a, b]) => occ.has((x + a) + ',' + (y + b))).length;
  const SPC = 1.0;                               // world units per cell
  const P = cells.map(([x, y, t], i) => ({
    x: (x - cx) * SPC, z: (y - cy) * SPC, y: 0.18 * Math.sin(i * 1.7) + 0.12 * Math.cos(x * 0.9 + y * 1.3), t,
    inner: neighbours(x, y) >= 3,
  }));
  const body = new THREE.Group(); scene.add(body);
  const membrane = new THREE.MeshPhysicalMaterial({
    vertexColors: true, roughness: 0.42, metalness: 0, clearcoat: 0.55, clearcoatRoughness: 0.3, transmission: 0.04, thickness: 1.2, envMapIntensity: 0.6,
    ior: 1.36, sheen: 0.35, sheenRoughness: 0.6, sheenColor: new THREE.Color(0xd8fff0),
    bumpMap: noiseTexture(), bumpScale: 0.6,
  });
  // A smooth field: one gaussian lobe per cell (flattened), fused where neighbours touch. The surface is
  // polygonised by marching cubes; colour is blended from the cells nearby and mottled for a living look.
  const pad = 1.6, half = span * SPC / 2 + pad;
  const res = Math.max(40, Math.min(110, Math.round(half * 2 / 0.16)));
  const mc = new MarchingCubes(res, membrane, true, true, 400000);
  mc.scale.set(half, half, half); mc.castShadow = true; mc.receiveShadow = true;
  mc.isolation = 50;
  const SIG2 = 2 * 0.36 * 0.36, FLAT = 1.7;
  const field = mc.field, pal = mc.palette, gsz = mc.size, gsz2 = mc.size2;
  field.fill(0); if (pal) pal.fill(0);
  const wsum = new Float32Array(mc.size3);
  const g2w = g => (g / (gsz - 1) * 2 - 1) * half;        // grid index → world coordinate
  const w2g = w => (w / half + 1) / 2 * (gsz - 1);
  P.forEach((p, i) => {
    const col = TINT[p.t].slice();
    if (p.t === 0) { const h = new THREE.Color().setHSL(((info.hue || 0) % 360) / 360, 0.42, 0.4); col[0] = h.r; col[1] = h.g; col[2] = h.b; }
    const amp = 100 * (p.t === 5 ? 1.15 : 1) * (0.94 + 0.12 * Math.abs(Math.sin(i * 12.9898)));
    const R = 1.25, gx0 = Math.max(1, Math.floor(w2g(p.x - R))), gx1 = Math.min(gsz - 2, Math.ceil(w2g(p.x + R)));
    const gy0 = Math.max(1, Math.floor(w2g(p.y - R / FLAT))), gy1 = Math.min(gsz - 2, Math.ceil(w2g(p.y + R / FLAT)));
    const gz0 = Math.max(1, Math.floor(w2g(p.z - R))), gz1 = Math.min(gsz - 2, Math.ceil(w2g(p.z + R)));
    for (let gz = gz0; gz <= gz1; gz++) { const dz = g2w(gz) - p.z;
      for (let gy = gy0; gy <= gy1; gy++) { const dy = (g2w(gy) - p.y) * FLAT;
        for (let gx = gx0; gx <= gx1; gx++) { const dx = g2w(gx) - p.x;
          const v = amp * Math.exp(-(dx * dx + dy * dy + dz * dz) / SIG2);
          if (v < 0.5) continue;
          const k = gx + gy * gsz + gz * gsz2;
          field[k] += v; wsum[k] += v;
          if (pal) { pal[k * 3] += col[0] * v; pal[k * 3 + 1] += col[1] * v; pal[k * 3 + 2] += col[2] * v; }
        } } }
  });
  if (pal) for (let k = 0; k < mc.size3; k++) if (wsum[k] > 0) {
    const m = 0.82 + 0.3 * vn(k % gsz, Math.floor(k / gsz) % gsz, Math.floor(k / gsz2));   // mottling
    pal[k * 3] = pal[k * 3] / wsum[k] * m; pal[k * 3 + 1] = pal[k * 3 + 1] / wsum[k] * m; pal[k * 3 + 2] = pal[k * 3 + 2] / wsum[k] * m;
  }
  mc.update();
  body.add(mc);
  body.updateMatrixWorld(true);

  // find the body's surface by casting rays at it, so organs sit on the skin
  const ray = new THREE.Raycaster();
  function surface(from, dir) {
    ray.set(from, dir.clone().normalize()); const h = ray.intersectObject(mc, false)[0];
    if (!h) return null; const nrm = h.face ? h.face.normal.clone().transformDirection(mc.matrixWorld) : dir.clone().negate();
    return { point: h.point, normal: nrm };
  }

  const flagella = [];
  const eyeMat = new THREE.MeshPhysicalMaterial({ color: 0x050508, roughness: 0.04, clearcoat: 1, clearcoatRoughness: 0.02 });
  const irisMat = new THREE.MeshStandardMaterial({ color: 0x9a7a2a, roughness: 0.35, emissive: 0x2a1a05 });
  const lipMat = new THREE.MeshPhysicalMaterial({ color: 0x7a1e1a, roughness: 0.45, clearcoat: 0.6, sheen: 0.4, bumpMap: noiseTexture(), bumpScale: 0.3 });
  const toothMat = new THREE.MeshStandardMaterial({ color: 0xf2ead8, roughness: 0.3 });
  const plateMat = new THREE.MeshPhysicalMaterial({ color: 0x4e463a, roughness: 0.5, metalness: 0.1, clearcoat: 0.9, clearcoatRoughness: 0.25,
    iridescence: 0.5, iridescenceIOR: 1.4, bumpMap: noiseTexture(), bumpScale: 0.8 });
  const neuroMat = new THREE.MeshStandardMaterial({ color: 0xb08cff, emissive: 0x6a3cff, emissiveIntensity: 0.9, roughness: 0.4 });
  const flagMat = new THREE.MeshPhysicalMaterial({ color: 0xe8e0d0, roughness: 0.45, transmission: 0.25, thickness: 0.1, sheen: 0.5 });
  const cxw = P.reduce((a, p) => a + p.x, 0) / n, czw = P.reduce((a, p) => a + p.z, 0) / n;
  const neurons = [];
  const UP = new THREE.Vector3(0, 1, 0);
  P.forEach((p, i) => {
    const out = new THREE.Vector3(p.x - cxw, 0, p.z - czw); if (out.length() < 1e-3) out.set(1, 0, 0); out.normalize();
    const top = () => surface(new THREE.Vector3(p.x, 5, p.z), new THREE.Vector3(0, -1, 0));
    const side = () => surface(new THREE.Vector3(p.x, p.y + 0.15, p.z).add(out.clone().multiplyScalar(4)), out.clone().negate());
    const orient = (obj, nrm) => obj.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nrm.clone().normalize());
    if (p.t === 4) {                       // eye: a glossy lens bulging from the skin
      const hit = side() || top(); if (!hit) return;
      const nrm = hit.normal.clone().add(UP.clone().multiplyScalar(0.5)).normalize();
      const g = new THREE.Group();
      g.add(new THREE.Mesh(new THREE.SphereGeometry(0.19, 32, 24), eyeMat));
      const iris = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.035, 12, 32), irisMat); iris.position.z = 0.16; g.add(iris);
      g.position.copy(hit.point).add(nrm.clone().multiplyScalar(0.06)); orient(g, nrm); body.add(g);
    } else if (p.t === 2) {                // mouth: muscular lip ring with teeth
      const hit = side() || top(); if (!hit) return;
      const g = new THREE.Group();
      g.add(new THREE.Mesh(new THREE.TorusGeometry(0.24, 0.09, 16, 36), lipMat));
      g.add(new THREE.Mesh(new THREE.CircleGeometry(0.2, 32), new THREE.MeshBasicMaterial({ color: 0x140303 })));
      for (let k = 0; k < 9; k++) {
        const a = k / 9 * Math.PI * 2, tooth = new THREE.Mesh(new THREE.ConeGeometry(0.035, 0.12, 8), toothMat);
        tooth.position.set(Math.cos(a) * 0.17, Math.sin(a) * 0.17, 0.02); tooth.rotation.z = a - Math.PI / 2; tooth.rotation.x = 0.5; g.add(tooth);
      }
      g.position.copy(hit.point).add(hit.normal.clone().multiplyScalar(0.02)); orient(g, hit.normal); body.add(g);
    } else if (p.t === 5) {                // armour: a ridged plate shingled on the back
      const hit = top(); if (!hit) return;
      const plate = new THREE.Mesh(new THREE.SphereGeometry(0.56, 28, 10, 0, Math.PI * 2, 0, Math.PI / 2.7), plateMat); plate.scale.y = 0.45;
      plate.position.copy(hit.point).add(new THREE.Vector3(0, -0.12, 0));
      plate.quaternion.setFromUnitVectors(UP, hit.normal.clone().normalize()); plate.rotateY(i * 0.7); plate.castShadow = true; body.add(plate);
    } else if (p.t === 7) {                // a nerve knot glowing just under the skin
      const hit = top(); if (!hit) return;
      const c = new THREE.Mesh(new THREE.IcosahedronGeometry(0.12, 2), neuroMat); c.position.copy(hit.point).add(new THREE.Vector3(0, -0.05, 0)); body.add(c); neurons.push(c);
    } else if (p.t === 3) {                // flagellum: a long whip that beats
      const hit = side(); const base = hit ? hit.point.clone() : new THREE.Vector3(p.x + out.x * 0.4, p.y, p.z + out.z * 0.4);
      const mesh = new THREE.Mesh(new THREE.BufferGeometry(), flagMat); mesh.castShadow = true; body.add(mesh);
      flagella.push({ base, dir: out.clone(), mesh, phase: i * 0.7, len: 2.2 + (i % 3) * 0.4 });
    }
  });
  function beat(t) {
    flagella.forEach(f => {
      const side = new THREE.Vector3(-f.dir.z, 0, f.dir.x), pts = [];
      for (let k = 0; k <= 16; k++) {
        const s = k / 16, a = Math.sin(t * 7 + f.phase - s * 5) * 0.45 * s;
        pts.push(f.base.clone().add(f.dir.clone().multiplyScalar(s * f.len)).add(side.clone().multiplyScalar(a)).add(new THREE.Vector3(0, Math.cos(t * 5 + s * 4 + f.phase) * 0.12 * s, 0)));
      }
      f.mesh.geometry.dispose();
      f.mesh.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 32, 0.06, 8, false);
      const pos = f.mesh.geometry.attributes.position;   // taper toward the tip
      for (let v = 0; v < pos.count; v++) {
        const seg = Math.floor(v / 9) / 32, c = pts[Math.min(16, Math.round(seg * 16))];
        const k = 1 - seg * 0.85; pos.setXYZ(v, c.x + (pos.getX(v) - c.x) * k, c.y + (pos.getY(v) - c.y) * k, c.z + (pos.getZ(v) - c.z) * k);
      }
      pos.needsUpdate = true; f.mesh.geometry.computeVertexNormals();
    });
  }
  const R = Math.max(2.2, span * SPC * 0.75 + 1.2);
  camera.position.set(R * 0.9, R * 0.85, R * 1.3); controls.target.set(0, 0, 0);
  floor.position.y = causMesh.position.y = -Math.max(1.6, span * 0.35) - 0.4;
  causMesh.position.y += 0.02;

  function size() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  size(); window.addEventListener('resize', size);
  let raf = 0, t0 = performance.now();
  function loop(now) {
    const t = (now - t0) / 1000;
    body.position.y = Math.sin(t * 0.8) * 0.12; body.rotation.z = Math.sin(t * 0.5) * 0.04;
    body.scale.setScalar(1 + Math.sin(t * 1.6) * 0.012);
    beat(t);
    neurons.forEach((m, i) => { m.material.emissiveIntensity = 0.6 + 0.5 * Math.max(0, Math.sin(t * 3 + i)); });
    caus.update(t);
    const p = snow.geometry.attributes.position;
    for (let i = 0; i < snowN; i++) { let y = p.getY(i) - 0.004; if (y < -3) y = 11; p.setY(i, y); }
    p.needsUpdate = true;
    controls.update(); renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }
  raf = requestAnimationFrame(loop);
  function close() {
    cancelAnimationFrame(raf); window.removeEventListener('resize', size); window.removeEventListener('keydown', onKey);
    renderer.dispose(); wrap.remove(); active = null;
  }
  const onKey = e => { if (e.key === 'Escape') close(); };
  window.addEventListener('keydown', onKey);
  wrap.querySelector('.close').onclick = close;
  wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
  active = { close };
}

function sandTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), img = g.createImageData(256, 256);
  for (let i = 0; i < 256 * 256; i++) { const v = 170 + Math.random() * 60; img.data[i * 4] = v; img.data[i * 4 + 1] = v * 0.93; img.data[i * 4 + 2] = v * 0.75; img.data[i * 4 + 3] = 255; }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(20, 20); t.colorSpace = THREE.SRGBColorSpace; return t;
}

function noiseTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), img = g.createImageData(256, 256);
  for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
    const v = 128 + 70 * (vn(x / 9, y / 9, 1) - 0.5) + 40 * (vn(x / 3, y / 3, 2) - 0.5);
    const k = (y * 256 + x) * 4; img.data[k] = img.data[k + 1] = img.data[k + 2] = v; img.data[k + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 3); return t;
}

function vn(x, y, z) {   // small value noise
  const h = (a, b, c) => { let n = Math.imul(a, 374761393) ^ Math.imul(b, 668265263) ^ Math.imul(c, 1274126177); n = Math.imul(n ^ (n >>> 13), 1103515245); return ((n ^ (n >>> 16)) >>> 0) / 4294967296; };
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z || 0), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = h(xi, yi, zi), b = h(xi + 1, yi, zi), c = h(xi, yi + 1, zi), d = h(xi + 1, yi + 1, zi);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

function causticsTexture() {
  // cellular (Voronoi edge) pattern: the bright web real sunlight makes through waves; two layers drift apart
  const N = 256, c = document.createElement('canvas'); c.width = c.height = N;
  const g = c.getContext('2d'), img = g.createImageData(N, N), pts = [];
  for (let i = 0; i < 28; i++) pts.push([Math.random() * N, Math.random() * N]);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    let d1 = 1e9, d2 = 1e9;
    for (const [px, py] of pts) for (let ox = -N; ox <= N; ox += N) for (let oy = -N; oy <= N; oy += N) {
      const d = Math.hypot(x - px - ox, y - py - oy); if (d < d1) { d2 = d1; d1 = d; } else if (d < d2) d2 = d;
    }
    const e = Math.pow(Math.max(0, 1 - (d2 - d1) / 9), 3);
    const k = (y * N + x) * 4; img.data[k] = 190 * e; img.data[k + 1] = 240 * e; img.data[k + 2] = 255 * e; img.data[k + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(7, 7);
  const t2 = t.clone(); t2.needsUpdate = true; t2.repeat.set(5.3, 5.3);
  return {
    texture: t, texture2: t2,
    update(time) { t.offset.set(time * 0.012, time * 0.007); t2.offset.set(-time * 0.009, time * 0.011); },
  };
}
