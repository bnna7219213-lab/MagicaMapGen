// C2 verification harness: compares the OLD CarveEdge (all four edges run the
// full edge length) against the FIXED CarveEdge (vertical edges reserve the
// corner strips: cursor=depth, endPos=edgeLen-depth) and classifies overlaps.
//
// Overlap classification is by intersection WIDTH, not raw boolean touch:
//   - genuine  : overlap in BOTH x and y by > WIDTH_EPS  -> real area clash
//   - sliver   : overlap narrower than WIDTH_EPS on an axis -> float32 rounding
//                on a shared edge between two consecutive same-edge lots.
// The old C2 defect (East/West strips carving into North/South corners) shows
// up as genuine overlaps with both dimensions ~depth (tens of units).
//
// RNG copied verbatim from sim.js (validated bit-exact vs 3 real Unity reports).
// Usage: node sim_c2.js
const f32 = Math.fround;
const WIDTH_EPS = 0.01; // 1/100 of a world unit; blocks are 80 units across

function hashSeed(seed, key) {
  let h = BigInt.asUintN(32, BigInt(seed | 0));
  for (const ch of key) { h ^= BigInt(ch.codePointAt(0)); h = BigInt.asUintN(32, h * 16777619n); }
  return Number(BigInt.asIntN(32, h));
}
function mix(z) {
  z = BigInt.asUintN(64, z + 0x9E3779B97F4A7C15n);
  let x = z;
  x = BigInt.asUintN(64, (x ^ (x >> 30n)) * 0xBF58476D1CE4E5B9n);
  x = BigInt.asUintN(64, (x ^ (x >> 27n)) * 0x94D049BB133111EBn);
  return [x ^ (x >> 31n), z];
}
class DetRandom {
  constructor(seed) {
    let z = BigInt.asUintN(64, BigInt.asUintN(64, BigInt(seed | 0)) + 0x9E3779B97F4A7C15n);
    let r; [r, z] = mix(z); this.s0 = r; [r, z] = mix(z); this.s1 = r;
    if (this.s0 === 0n && this.s1 === 0n) this.s1 = 1n;
  }
  nextUlong() {
    let s1 = this.s0, s0 = this.s1; this.s0 = s0;
    s1 = BigInt.asUintN(64, s1 ^ (s1 << 23n));
    this.s1 = BigInt.asUintN(64, s1 ^ s0 ^ (s1 >> 18n) ^ (s0 >> 5n));
    return BigInt.asUintN(64, this.s1 + s0);
  }
  nextInt(min, max) { if (max <= min) return min; return min + Number(this.nextUlong() % BigInt(max - min)); }
  nextFloat(min, max) {
    const shifted = this.nextUlong() >> 11n;
    const t = f32(f32(Number(shifted)) * f32(1 / 9007199254740992));
    const lo = f32(min), hi = f32(max);
    return f32(lo + f32(f32(hi - lo) * t));
  }
  chance(p) { return this.nextFloat(0, 1) < p; }
}

const PROFILE = { blockSize: 80, roadWidth: 12, sidewalkWidth: 3, lotSizeRange: { x: 16, y: 30 } };

function carveEdge(P, block, rand, facing, lots, fixed) {
  const r = block.rect;
  const horizontal = facing === 'North' || facing === 'South';
  const edgeLen = f32(horizontal ? r.w : r.h);
  const depth = f32(Math.min(P.maxLot, f32(f32(horizontal ? r.h : r.w) * f32(0.45))));
  if (depth < P.minLot) return;
  let cursor = 0, endPos = edgeLen;
  if (fixed && !horizontal) { cursor = depth; endPos = f32(edgeLen - depth); } // <-- the C2 fix
  while (f32(endPos - cursor) >= P.minLot) {
    const remaining = f32(endPos - cursor);
    let w = f32(Math.min(rand.nextFloat(P.minLot, P.maxLot), remaining));
    if (f32(remaining - w) < P.minLot) w = remaining;
    let lot;
    switch (facing) {
      case 'North': lot = { x: f32(r.x + cursor), y: f32(r.yMax - depth), w, h: depth, facing }; break;
      case 'South': lot = { x: f32(r.x + cursor), y: r.y, w, h: depth, facing }; break;
      case 'East':  lot = { x: f32(r.xMax - depth), y: f32(r.y + cursor), w: depth, h: w, facing }; break;
      default:      lot = { x: r.x, y: f32(r.y + cursor), w: depth, h: w, facing }; break;
    }
    if (!rand.chance(P.lotFillRatio)) { cursor = f32(cursor + w); continue; }
    lots.push(lot);
    rand.nextInt(0, 2147483647);
    cursor = f32(cursor + w);
  }
}

function runOne(seed, grid, lotFillRatio, fixed) {
  const pitch = PROFILE.blockSize + PROFILE.roadWidth, half = PROFILE.roadWidth * 0.5, sw = PROFILE.sidewalkWidth;
  const P = { minLot: Math.max(4, PROFILE.lotSizeRange.x), maxLot: Math.max(Math.max(4, PROFILE.lotSizeRange.x), PROFILE.lotSizeRange.y), lotFillRatio };
  let totalLots = 0, genuine = 0, sliver = 0, maxGenuineArea = 0;
  const ex = [];
  for (let by = 0; by < grid; by++) for (let bx = 0; bx < grid; bx++) {
    const ox = half + bx * pitch + half, oz = half + by * pitch + half;
    const iw = Math.max(1, PROFILE.blockSize - 2 * sw);
    const block = { rect: { x: ox + sw, y: oz + sw, w: iw, h: iw } };
    block.rect.xMax = block.rect.x + block.rect.w; block.rect.yMax = block.rect.y + block.rect.h;
    const rand = new DetRandom(hashSeed(seed, `world/block_${bx}_${by}`));
    const lots = [];
    for (const f of ['North', 'South', 'East', 'West']) carveEdge(P, block, rand, f, lots, fixed);
    totalLots += lots.length;
    for (let i = 0; i < lots.length; i++) for (let j = i + 1; j < lots.length; j++) {
      const a = lots[i], b = lots[j];
      const dx = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const dy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (dx > 0 && dy > 0) {
        if (dx > WIDTH_EPS && dy > WIDTH_EPS) {
          genuine++; const area = dx * dy; if (area > maxGenuineArea) maxGenuineArea = area;
          if (ex.length < 4) ex.push(`    ${a.facing}[${a.x.toFixed(1)},${(a.x+a.w).toFixed(1)}]x[${a.y.toFixed(1)},${(a.y+a.h).toFixed(1)}] vs ${b.facing}[${b.x.toFixed(1)},${(b.x+b.w).toFixed(1)}]x[${b.y.toFixed(1)},${(b.y+b.h).toFixed(1)}] area=${area.toFixed(1)}`);
        } else sliver++;
      }
    }
  }
  return { totalLots, genuine, sliver, maxGenuineArea, ex };
}

const seeds = [12345, 1, 20261002, 999983, 42], grids = [2, 4, 8, 16], fills = [0.5, 0.85, 1.0];
for (const mode of [false, true]) {
  let lots = 0, genuine = 0, sliver = 0, maxArea = 0, worstCombo = null, ex = [];
  for (const s of seeds) for (const g of grids) for (const f of fills) {
    const r = runOne(s, g, f, mode);
    lots += r.totalLots; sliver += r.sliver;
    if (r.genuine > 0) { genuine += r.genuine; if (!worstCombo || r.maxGenuineArea > maxArea) { maxArea = r.maxGenuineArea; worstCombo = `seed=${s} grid=${g} fill=${f}`; ex = r.ex; } }
  }
  console.log(`\n=== ${mode ? 'FIXED CarveEdge (corner-skip)' : 'OLD CarveEdge (full-length)'} ===`);
  console.log(`  total lots across sweep : ${lots}`);
  console.log(`  GENUINE overlaps (>0.01 in both axes) : ${genuine}   max area ${maxArea.toFixed(1)}${worstCombo ? '  @ ' + worstCombo : ''}`);
  console.log(`  float slivers (shared-edge rounding)  : ${sliver}   (harmless, sub-0.01 wide)`);
  for (const e of ex) console.log(e);
}
console.log(`\nWIDTH_EPS=${WIDTH_EPS}; genuine = real area clash, sliver = float32 shared-edge noise.`);
