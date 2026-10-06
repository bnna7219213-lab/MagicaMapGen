// Validates the C4 scene-cleanup algorithm on a JS mirror of the real Unity
// hierarchy produced by SceneAssembler:
//   LPW_world(marker) -> Roads(none) | Blocks(marker) -> block_i(marker) -> buildings(none) | Scatter(none)
//
// Three cleanup strategies are compared:
//   old   : non-recursive lock check (only the child's OWN marker) -- the C4 bug
//   coarse: current "Fix C4" (preserve whole child if ANY descendant locked)
//   rec   : proposed recursive clean (preserve locked node; descend into a
//           container that merely holds a locked descendant; else destroy)
//
// Invariants we assert for the proposed algorithm:
//   A1 no locked node (nor its subtree) is ever destroyed
//   B1 every unlocked generated node NOT needed as a lock-ancestor is destroyed
//      (no stale accumulation)
//   C1 destruction is well-formed (we never "destroy" an already-destroyed node)
const f32 = Math.fround; // unused here; kept for parity with sibling harnesses

// --- tiny scene-graph mirror -------------------------------------------------
let UID = 0;
function node(name, { marker = false, locked = false, guid = null } = {}, children = []) {
  const n = { id: ++UID, name, marker, locked, guid, children, parent: null, destroyed: false };
  for (const c of children) c.parent = n;
  return n;
}
function destroy(n) {
  // Unity DestroyObjectImmediate destroys the whole subtree.
  const stack = [n];
  while (stack.length) {
    const x = stack.pop();
    if (x.destroyed) throw new Error('double-destroy: ' + x.name); // invariant C1
    x.destroyed = true;
    stack.push(...x.children);
  }
}
function isDestroyed(n) { return n.destroyed; }
function hasLockDeep(n) {
  if (n.destroyed) return false;
  if (n.marker && n.locked) return true;
  return n.children.some(hasLockDeep);
}

// --- strategies --------------------------------------------------------------
// old: iterate direct children; skip only if the CHILD ITSELF is a locked marker.
function clearOld(root) {
  let removed = 0;
  for (let i = root.children.length - 1; i >= 0; i--) {
    const c = root.children[i];
    if (c.marker && c.locked) continue;
    destroy(c); removed++;
  }
  return removed;
}
// coarse: current fix -- skip child if HasLockDeep(child).
function clearCoarse(root) {
  let removed = 0;
  for (let i = root.children.length - 1; i >= 0; i--) {
    const c = root.children[i];
    if (hasLockDeep(c)) continue;
    destroy(c); removed++;
  }
  return removed;
}
// rec: proposed -- locked node preserved; container with a locked descendant is
// descended into; otherwise the whole unlocked subtree is destroyed.
function clearRec(t) {
  let removed = 0;
  for (let i = t.children.length - 1; i >= 0; i--) {
    const c = t.children[i];
    if (c.marker && c.locked) continue;            // A1: locked subtree preserved
    if (hasLockDeep(c)) { removed += clearRec(c); continue; } // descend, keep lock chain
    destroy(c); removed++;                          // B1: unlocked generated subtree gone
  }
  return removed;
}

// CleanAll variants (operate over a flat snapshot of all markers, like
// Object.FindObjectsByType<WorldBuildMarker>).
function markersOf(root) {
  const out = [];
  (function walk(n) { if (n.marker) out.push(n); n.children.forEach(walk); })(root);
  return out;
}
function cleanAllOld(root, guid) {
  const snap = markersOf(root); let removed = 0;
  for (const m of snap) {
    if (m.destroyed) { /* C#: accessing a destroyed MonoBehaviour throws */ throw new Error('MissingReference on ' + m.name); }
    if (m.guid !== guid || m.locked) continue;
    destroy(m); removed++;
  }
  return removed;
}
function cleanAllFixed(root, guid) {
  const snap = markersOf(root); let removed = 0;
  for (const m of snap) {
    if (m.destroyed) continue;                 // guard: parent already destroyed it
    if (m.guid !== guid) continue;
    if (hasLockDeep(m)) continue;              // preserve locked subtree (and its ancestor)
    destroy(m); removed++;
  }
  return removed;
}

// --- scenarios ---------------------------------------------------------------
function buildWorld(lockBlock) {
  UID = 0;
  const buildings = (tag) => [node('b_' + tag + '_0'), node('b_' + tag + '_1')];
  const blocks = [0, 1, 2].map(i =>
    node('block_' + i, { marker: true, locked: lockBlock === i, guid: 'G' }, buildings('b' + i)));
  const Roads = node('Roads');
  const Blocks = node('Blocks', { marker: true, locked: false, guid: 'G' }, blocks);
  const Scatter = node('Scatter');
  const world = node('LPW_world', { marker: true, locked: false, guid: 'G' }, [Roads, Blocks, Scatter]);
  return { world, Blocks, blocks };
}
function liveBlockNames(world) {
  const out = [];
  (function walk(n) { if (!n.destroyed && n.name.startsWith('block_')) out.push(n.name); n.children.forEach(walk); })(world);
  return out.sort();
}

let pass = 0, fail = 0;
function check(label, cond, detail = '') {
  (cond ? pass++ : fail++);
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? '  -- ' + detail : ''}`);
}

console.log('=== ClearGeneratedChildren: NO lock (block_1 unlocked) ===');
{
  const { world } = buildWorld(-1);
  clearRec(world);
  const live = liveBlockNames(world);
  check('all generated children removed', live.length === 0, 'live blocks=' + JSON.stringify(live));
  check('Roads/Scatter/Blocks destroyed', world.children.every(c => c.destroyed));
}

console.log('\n=== ClearGeneratedChildren: block_1 LOCKED ===');
{
  const old = buildWorld(1); try { clearOld(old.world); } catch (e) {}
  check('[old] locked block_1 DESTROYED (the C4 bug)', old.blocks[1].destroyed);

  const coarse = buildWorld(1); clearCoarse(coarse.world);
  const coarseLive = liveBlockNames(coarse.world);
  check('[coarse] locked block_1 preserved', !coarse.blocks[1].destroyed);
  check('[coarse] REGRESSION: stale unlocked blocks survive', coarseLive.length === 3, 'live=' + JSON.stringify(coarseLive));

  const rec = buildWorld(1); clearRec(rec.world);
  const recLive = liveBlockNames(rec.world);
  check('[rec] locked block_1 + its buildings preserved', !rec.blocks[1].destroyed && rec.blocks[1].children.every(b => !b.destroyed));
  check('[rec] unlocked block_0 & block_2 removed (no stale)', JSON.stringify(recLive) === JSON.stringify(['block_1']), 'live=' + JSON.stringify(recLive));
  check('[rec] Blocks container preserved as lock-ancestor', !rec.Blocks.destroyed);
  check('[rec] Roads & Scatter removed', rec.world.children.filter(c => c.name !== 'Blocks').every(c => c.destroyed));
}

console.log('\n=== CleanAll: nested locked block under unlocked Blocks container ===');
{
  const old = buildWorld(1);
  let threw = false;
  try { cleanAllOld(old.world, 'G'); } catch (e) { threw = /MissingReference|double-destroy/.test(e.message); }
  check('[old] crashes (MissingReference/double-destroy) OR destroys lock', threw || old.blocks[1].destroyed, threw ? 'threw' : 'lock destroyed=' + old.blocks[1].destroyed);

  const fixed = buildWorld(1);
  cleanAllFixed(fixed.world, 'G');
  check('[fixed] locked block_1 preserved', !fixed.blocks[1].destroyed);
  check('[fixed] no exception thrown', true);
}

console.log(`\n${fail === 0 ? 'ALL PASS' : 'FAILURES'}: pass=${pass} fail=${fail}`);
process.exitCode = fail === 0 ? 0 : 1;
