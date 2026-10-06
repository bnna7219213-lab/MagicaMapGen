using System;
using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Top-level orchestration of the pure-data generation pipeline:
    /// roads -> blocks/lots -> building parameters -> scatter. Output is a
    /// BuildPlan that the scene assembly layer turns into GameObjects.
    /// </summary>
    public sealed class WorldPlanGenerator
    {
        public BuildPlan Generate(WorldBuildProfile profile, WorldBuildReport report)
        {
            var ctx = new GenerationContext(profile.seed, "world", report);
            var plan = new BuildPlan { seed = profile.seed, schemaVersion = profile.schemaVersion };
            report.theme = profile.theme.ToString();
            report.gridWidth = profile.blockCount.x;
            report.gridHeight = profile.blockCount.y;

            plan.roadGraph = new RoadNetworkGenerator().Generate(profile, ctx);
            plan.blocks = new BlockSubdivisionGenerator().Generate(profile, ctx);

            var buildings = new BuildingGenerator();
            foreach (var block in plan.blocks)
                buildings.ResolveLots(profile, block, ctx);

            plan.scatter = new ScatterGenerator().Generate(profile, plan.roadGraph, plan.blocks, ctx);

            int buildingCount = 0;
            var archetypeCounts = new Dictionary<BuildingArchetype, int>();
            foreach (var b in plan.blocks)
            foreach (var lot in b.lots)
            {
                buildingCount++;
                if (!archetypeCounts.ContainsKey(lot.archetype)) archetypeCounts[lot.archetype] = 0;
                archetypeCounts[lot.archetype]++;
            }
            report.buildingCount = buildingCount;
            foreach (BuildingArchetype archetype in Enum.GetValues(typeof(BuildingArchetype)))
                if (archetypeCounts.TryGetValue(archetype, out int count))
                    report.buildingArchetypes.Add(new BuildingArchetypeCount { archetype = archetype.ToString(), count = count });
            return plan;
        }
    }
}
