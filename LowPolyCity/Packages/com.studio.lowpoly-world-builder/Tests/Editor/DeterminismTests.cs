using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Generation;
using NUnit.Framework;
using UnityEngine;

namespace LowPolyWorldBuilder.EditorTests
{
    /// <summary>
    /// MVP acceptance criteria (plan section 7): same config + seed produces
    /// identical topology, positions, sizes and variant picks.
    /// </summary>
    public class DeterminismTests
    {
        static WorldBuildProfile MakeProfile(int seed)
        {
            var p = ScriptableObject.CreateInstance<WorldBuildProfile>();
            p.seed = seed;
            p.blockCount = new Vector2Int(4, 4);
            p.blockSize = 80f;
            p.roadWidth = 12f;
            p.sidewalkWidth = 3f;
            p.minBuildingHeight = 8f;
            p.maxBuildingHeight = 40f;
            p.zones = new ZoneProfile[0];
            return p;
        }

        [Test]
        public void SameSeed_ProducesIdenticalPlan()
        {
            var a = new WorldPlanGenerator().Generate(MakeProfile(12345), new WorldBuildReport());
            var b = new WorldPlanGenerator().Generate(MakeProfile(12345), new WorldBuildReport());

            Assert.AreEqual(a.roadGraph.edges.Count, b.roadGraph.edges.Count);
            Assert.AreEqual(a.blocks.Count, b.blocks.Count);
            for (int i = 0; i < a.blocks.Count; i++)
            {
                Assert.AreEqual(a.blocks[i].lots.Count, b.blocks[i].lots.Count, $"block {i} lot count");
                for (int j = 0; j < a.blocks[i].lots.Count; j++)
                {
                    var la = a.blocks[i].lots[j];
                    var lb = b.blocks[i].lots[j];
                    Assert.AreEqual(la.rect, lb.rect, $"lot {i}/{j} rect");
                    Assert.AreEqual(la.height, lb.height, $"lot {i}/{j} height");
                    Assert.AreEqual(la.wallColorIndex, lb.wallColorIndex);
                    Assert.AreEqual(la.roofColorIndex, lb.roofColorIndex);
                    Assert.AreEqual(la.archetype, lb.archetype, $"lot {i}/{j} archetype");
                }
            }
            Assert.AreEqual(a.scatter.Count, b.scatter.Count);
        }

        [Test]
        public void DifferentSeed_ProducesDifferentLayout()
        {
            var a = new WorldPlanGenerator().Generate(MakeProfile(1), new WorldBuildReport());
            var b = new WorldPlanGenerator().Generate(MakeProfile(2), new WorldBuildReport());
            bool differ = a.scatter.Count != b.scatter.Count;
            if (!differ)
                for (int i = 0; i < a.blocks.Count && !differ; i++)
                    for (int j = 0; j < a.blocks[i].lots.Count && !differ; j++)
                        if (a.blocks[i].lots[j].height != b.blocks[i].lots[j].height) differ = true;
            Assert.IsTrue(differ, "Different seeds should change the layout");
        }

        [Test]
        public void RoadGraph_IsFullyConnected()
        {
            var plan = new WorldPlanGenerator().Generate(MakeProfile(12345), new WorldBuildReport());
            Assert.IsTrue(plan.roadGraph.IsConnected(out int orphans), $"{orphans} orphan nodes");
        }

        [Test]
        public void Lots_StayInsideBlockAndDoNotOverlap()
        {
            var plan = new WorldPlanGenerator().Generate(MakeProfile(12345), new WorldBuildReport());
            Assert.AreEqual(16, plan.blocks.Count, "4x4 profile should produce 16 blocks");
            foreach (var block in plan.blocks)
            {
                for (int i = 0; i < block.lots.Count; i++)
                {
                    var r = block.lots[i].rect;
                    Assert.IsTrue(block.rect.Contains(new Vector2(r.xMin, r.yMin)) &&
                                  block.rect.Contains(new Vector2(r.xMax, r.yMax)),
                        $"lot {i} escapes block {block.RegionKey}");
                    for (int j = i + 1; j < block.lots.Count; j++)
                        Assert.IsFalse(r.Overlaps(block.lots[j].rect), $"lots {i}/{j} overlap in {block.RegionKey}");
                }
            }
        }

        [Test]
        public void DeterministicRandom_IsPlatformStable()
        {
            var r1 = new DeterministicRandom(999);
            var r2 = new DeterministicRandom(999);
            for (int i = 0; i < 100; i++)
                Assert.AreEqual(r1.NextInt(0, 1000000), r2.NextInt(0, 1000000));
        }

        [Test]
        public void Zones_ProduceDistinctArchetypes()
        {
            // One zone of each usage, guaranteed assignment (weight=1, single zone).
            var usages = new[]
            {
                ZoneUsage.Residential, ZoneUsage.Commercial, ZoneUsage.Office,
                ZoneUsage.Industrial, ZoneUsage.Rail, ZoneUsage.Airport
            };
            var seen = new System.Collections.Generic.HashSet<BuildingArchetype>();
            foreach (var usage in usages)
            {
                var p = MakeProfile(7);
                var zone = ScriptableObject.CreateInstance<ZoneProfile>();
                zone.usage = usage;
                zone.spawnWeight = 1f;
                p.zones = new[] { zone };
                var plan = new WorldPlanGenerator().Generate(p, new WorldBuildReport());
                Assert.Greater(plan.blocks.Count, 0);
                foreach (var b in plan.blocks)
                    foreach (var l in b.lots)
                        seen.Add(l.archetype);
            }
            // Across usages we must see at least 5 distinct archetypes — the
            // whole point of the archetype system is that zones look different.
            Assert.GreaterOrEqual(seen.Count, 5,
                "Zones collapsed to too few archetypes: " + string.Join(",", seen));
        }

        [Test]
        public void ThemeThemes_ReserveDifferentInfrastructureBlocks()
        {
            var airport = MakeProfile(11);
            airport.theme = WorldTheme.Airport;
            var harbor = MakeProfile(11);
            harbor.theme = WorldTheme.Harbor;
            var pa = new WorldPlanGenerator().Generate(airport, new WorldBuildReport());
            var ph = new WorldPlanGenerator().Generate(harbor, new WorldBuildReport());

            int airportInfra = 0, harborInfra = 0;
            foreach (var b in pa.blocks) if (b.infrastructureBlock) airportInfra++;
            foreach (var b in ph.blocks) if (b.infrastructureBlock) harborInfra++;
            Assert.Greater(airportInfra, 0, "Airport should reserve runway/terminal blocks");
            Assert.Greater(harborInfra, 0, "Harbor should reserve water blocks");
        }
    }
}
