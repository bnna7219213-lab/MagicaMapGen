using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Generation;
using NUnit.Framework;
using UnityEngine;

namespace LowPolyWorldBuilder.EditorTests
{
    /// <summary>
    /// Regression guard for the theme-building fix: transport themes must read
    /// as their signature buildings even when the zone reference is missing or
    /// legacy, instead of collapsing to House. The fix lives in
    /// BuildingGenerator.ResolveArchetype (theme is resolved before any zone
    /// fallback). These tests lock that behaviour so a future edit to the
    /// archetype switch cannot silently re-introduce the regression.
    /// </summary>
    public class ThemeRegressionTests
    {
        static WorldBuildProfile MakeProfile(WorldTheme theme)
        {
            var p = ScriptableObject.CreateInstance<WorldBuildProfile>();
            p.seed = 12345;
            p.blockCount = new Vector2Int(4, 4);
            p.blockSize = 80f;
            p.roadWidth = 12f;
            p.sidewalkWidth = 3f;
            p.minBuildingHeight = 8f;
            p.maxBuildingHeight = 40f;
            p.theme = theme;
            p.zones = null; // the regression scenario: missing / legacy zone assets
            return p;
        }

        static readonly Dictionary<WorldTheme, BuildingArchetype[]> Expected =
            new Dictionary<WorldTheme, BuildingArchetype[]>
        {
            { WorldTheme.Railway, new[] { BuildingArchetype.Station, BuildingArchetype.RailDepot } },
            { WorldTheme.Metro,   new[] { BuildingArchetype.MetroStation, BuildingArchetype.MetroTower } },
            { WorldTheme.Harbor,  new[] { BuildingArchetype.HarborWarehouse, BuildingArchetype.HarborSilo, BuildingArchetype.Lighthouse } },
            { WorldTheme.Airport, new[] { BuildingArchetype.Hangar, BuildingArchetype.Terminal, BuildingArchetype.ControlTower } },
        };

        [TestCase(WorldTheme.Railway)]
        [TestCase(WorldTheme.Metro)]
        [TestCase(WorldTheme.Harbor)]
        [TestCase(WorldTheme.Airport)]
        public void TransportThemes_NeverCollapseToHouse_WhenZonesMissing(WorldTheme theme)
        {
            var plan = new WorldPlanGenerator().Generate(MakeProfile(theme), new WorldBuildReport());

            var allowed = new HashSet<BuildingArchetype>(Expected[theme]);
            var violations = new List<string>();
            int lotCount = 0;
            foreach (var block in plan.blocks)
                foreach (var lot in block.lots)
                {
                    lotCount++;
                    if (lot.archetype == BuildingArchetype.House)
                        violations.Add(block.RegionKey + "/" + lot.subSeed + ": House (theme " + theme + ")");
                    if (!allowed.Contains(lot.archetype))
                        violations.Add(block.RegionKey + "/" + lot.subSeed + ": " + lot.archetype + " not in theme set");
                }

            Assert.Greater(lotCount, 0, "Profile produced no lots; test would pass vacuously.");
            Assert.IsEmpty(violations,
                "Theme " + theme + " produced unexpected/regressed buildings:\n" + string.Join("\n", violations));
        }

        [Test]
        public void TransportThemes_UseMultipleSignatureBuildings()
        {
            foreach (var kv in Expected)
            {
                var plan = new WorldPlanGenerator().Generate(MakeProfile(kv.Key), new WorldBuildReport());
                var seen = new HashSet<BuildingArchetype>();
                foreach (var block in plan.blocks)
                    foreach (var lot in block.lots)
                        seen.Add(lot.archetype);
                Assert.GreaterOrEqual(seen.Count, 2,
                    "Theme " + kv.Key + " should mix at least 2 signature buildings, saw " + seen.Count);
            }
        }

        [Test]
        public void CityTheme_StillFallsBackToHouse_WhenZonesMissing()
        {
            var plan = new WorldPlanGenerator().Generate(MakeProfile(WorldTheme.City), new WorldBuildReport());
            bool anyHouse = false;
            foreach (var block in plan.blocks)
                foreach (var lot in block.lots)
                    if (lot.archetype == BuildingArchetype.House) { anyHouse = true; break; }
            Assert.IsTrue(anyHouse,
                "City with missing zones must still fall back to House; the fallback must not be broken by the theme fix.");
        }
    }
}
