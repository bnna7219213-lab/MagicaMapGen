// Reimplements LowPolyWorldBuilder's DeterministicRandom + CarveEdge exactly,
// to check the "lots must not overlap" acceptance criterion (plan section 7).
const M64 = (1n << 64n) - 1n;
const f32 = Math.fround;

function hashSeed(seed, key) {
  let h = BigInt.asUintN(32, BigInt(seed | 0));
  for (const ch of key) {
    h ^= BigInt(ch.codePointAt(0));
    h = BigInt.asUintN(32, h * 16777619n);
  }
  // (int)h  -> signed 32-bit
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
    // (ulong)seed : C# int -> ulong sign-extends
    let z = BigInt.asUintN(64, BigInt.asUintN(64, BigInt(seed | 0)) + 0x9E3779B97F4A7C15n);
    let r;
    [r, z] = mix(z); this.s0 = r;
    [r, z] = mix(z); this.s1 = r;
    if (this.s0 === 0n && this.s1 === 0n) this.s1 = 1n;
  }
  nextUlong() {
    let s1 = this.s0, s0 = this.s1;
    this.s0 = s0;
    s1 = BigInt.asUintN(64, s1 ^ (s1 << 23n));
    this.s1 = BigInt.asUintN(64, s1 ^ s0 ^ (s1 >> 18n) ^ (s0 >> 5n));
    return BigInt.asUintN(64, this.s1 + s0);
  }
  nextInt(min, max) {
    if (max <= min) return min;
    const span = BigInt(max - min);
    return min + Number(this.nextUlong() % span);
  }
  nextFloat(min, max) {
    // C#: float t = (float)(NextUlong() >> 11) * (1f / 9007199254740992f);
    //     return min + (max - min) * t;   -- every op rounds to float32
    const shifted = this.nextUlong() >> 11n;   // <= 2^53, exact as double
    const t = f32(f32(Number(shifted)) * f32(1 / 9007199254740992));
    const lo = f32(min), hi = f32(max);
    return f32(lo + f32(f32(hi - lo) * t));
  }
  chance(p) { return this.nextFloat(0, 1) < p; }
}

// --- profile: matches DeterminismTests.MakeProfile + WorldBuildProfile defaults
// Overridable: node sim.js <seed> <grid> <lotFillRatio>
const P = {
  seed: Number(process.argv[2] ?? 12345),
  blockCount: { x: Number(process.argv[3] ?? 4), y: Number(process.argv[3] ?? 4) },
  blockSize: 80, roadWidth: 12,
  sidewalkWidth: 3,
  lotFillRatio: Number(process.argv[4] ?? 0.85),
  lotSizeRange: { x: 16, y: 30 },
};
const pitch = P.blockSize + P.roadWidth;
const half = P.roadWidth * 0.5;
const sw = P.sidewalkWidth;
const minLot = Math.max(4, P.lotSizeRange.x);
const maxLot = Math.max(minLot, P.lotSizeRange.y);

function carveEdge(block, rand, facing, lots) {
  const r = block.rect;
  const horizontal = facing === 'North' || facing === 'South';
  const edgeLen = f32(horizontal ? r.w : r.h);
  const depth = f32(Math.min(maxLot, f32(f32(horizontal ? r.h : r.w) * f32(0.45))));
  if (depth < minLot) return;
  let cursor = 0;
  while (f32(edgeLen - cursor) >= minLot) {
    let w = f32(Math.min(rand.nextFloat(minLot, maxLot), f32(edgeLen - cursor)));
    if (f32(f32(edgeLen - cursor) - w) < minLot) w = f32(edgeLen - cursor);
    let lot;
    switch (facing) {
      case 'North': lot = { x: f32(r.x + cursor), y: f32(r.yMax - depth), w, h: depth, facing }; break;
      case 'South': lot = { x: f32(r.x + cursor), y: r.y, w, h: depth, facing }; break;
      case 'East':  lot = { x: f32(r.xMax - depth), y: f32(r.y + cursor), w: depth, h: w, facing }; break;
      default:      lot = { x: r.x, y: f32(r.y + cursor), w: depth, h: w, facing }; break;
    }
    if (!rand.chance(P.lotFillRatio)) { cursor = f32(cursor + w); continue; }
    lots.push(lot);
    rand.nextInt(0, 2147483647);   // LotData.subSeed consumes the stream
    cursor = f32(cursor + w);
  }
}

let totalLots = 0, blocksWithOverlap = 0, overlapPairs = 0;
const examples = [];
let containsInclusiveFail = 0, containsExclusiveFail = 0;

for (let by = 0; by < P.blockCount.y; by++) {
  for (let bx = 0; bx < P.blockCount.x; bx++) {
    const ox = half + bx * pitch + half;
    const oz = half + by * pitch + half;
    const iw = Math.max(1, P.blockSize - 2 * sw);
    const block = { rect: { x: ox + sw, y: oz + sw, w: iw, h: iw } };
    block.rect.xMax = block.rect.x + block.rect.w;
    block.rect.yMax = block.rect.y + block.rect.h;

    const rand = new DetRandom(hashSeed(P.seed, `world/block_${bx}_${by}`));
    const lots = [];
    carveEdge(block, rand, 'North', lots);
    carveEdge(block, rand, 'South', lots);
    carveEdge(block, rand, 'East', lots);
    carveEdge(block, rand, 'West', lots);
    totalLots += lots.length;

    // Unity Rect.Overlaps: other.xMax > xMin && other.xMin < xMax && other.yMax > yMin && other.yMin < yMax
    let bo = 0;
    for (let i = 0; i < lots.length; i++) {
      const a = lots[i];
      const axm = a.x + a.w, aym = a.y + a.h;
      const R = block.rect;
      const inIncl = (px, py) => px >= R.x && px <= R.xMax && py >= R.y && py <= R.yMax;
      const inExcl = (px, py) => px >= R.x && px <  R.xMax && py >= R.y && py <  R.yMax;
      if (!(inIncl(a.x, a.y) && inIncl(axm, aym))) containsInclusiveFail++;
      if (!(inExcl(a.x, a.y) && inExcl(axm, aym))) containsExclusiveFail++;
      for (let j = i + 1; j < lots.length; j++) {
        const b = lots[j];
        if (b.x + b.w > a.x && b.x < a.x + a.w && b.y + b.h > a.y && b.y < a.y + a.h) {
          bo++; overlapPairs++;
          if (examples.length < 5) examples.push({
            block: `block_${bx}_${by}`,
            A: `${a.facing} x[${a.x.toFixed(1)},${(a.x + a.w).toFixed(1)}] y[${a.y.toFixed(1)},${(a.y + a.h).toFixed(1)}]`,
            B: `${b.facing} x[${b.x.toFixed(1)},${(b.x + b.w).toFixed(1)}] y[${b.y.toFixed(1)},${(b.y + b.h).toFixed(1)}]`,
          });
        }
      }
    }
    if (bo > 0) blocksWithOverlap++;
  }
}

console.log(`seed=${P.seed} grid=${P.blockCount.x}x${P.blockCount.y}`);
console.log(`total lots            : ${totalLots}`);
console.log(`blocks with overlap   : ${blocksWithOverlap}/${P.blockCount.x*P.blockCount.y}`);
console.log(`overlapping lot pairs : ${overlapPairs}`);
console.log(`Rect.Contains max-corner failures (inclusive reading): ${containsInclusiveFail}`);
console.log(`Rect.Contains max-corner failures (exclusive reading): ${containsExclusiveFail}`);
console.log('examples:');
for (const e of examples) console.log(`  ${e.block}\n    A ${e.A}\n    B ${e.B}`);
