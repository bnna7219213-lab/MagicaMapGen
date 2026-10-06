using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;

namespace LowPolyWorldBuilder.Generation
{
    /// <summary>
    /// Resolves per-lot building parameters from the zone config. The zone's
    /// ZoneUsage is mapped to a concrete BuildingArchetype so the geometry
    /// layer produces visually distinct buildings per district instead of one
    /// shared box template (plan 3.1 item 3: residential/commercial/office/
    /// factory variants from configuration + module combination).
    /// </summary>
    public sealed class BuildingGenerator
    {
        public void ResolveLots(WorldBuildProfile profile, CityBlock block, GenerationContext ctx)
        {
            ZoneProfile zone = null;
            if (profile.zones != null && block.zoneIndex >= 0 && block.zoneIndex < profile.zones.Length)
                zone = profile.zones[block.zoneIndex];

            foreach (var lot in block.lots)
            {
                var rand = new DeterministicRandom(
                    GenerationContext.HashSeed(ctx.Seed, block.RegionKey + "/lot_" + lot.subSeed));

                float hMul = zone != null ? rand.NextFloat(zone.heightMultiplier.x, zone.heightMultiplier.y) : 1f;
                lot.height = UnityEngine.Mathf.Clamp(
                    rand.NextFloat(profile.minBuildingHeight, profile.maxBuildingHeight) * hMul,
                    3f, 200f);

                int wallCount = profile.palette != null && profile.palette.buildingWalls != null
                    ? profile.palette.buildingWalls.Length : 0;
                int roofCount = profile.palette != null && profile.palette.buildingRoofs != null
                    ? profile.palette.buildingRoofs.Length : 0;
                lot.wallColorIndex = wallCount > 0 ? rand.NextInt(0, wallCount) : 0;
                lot.roofColorIndex = roofCount > 0 ? rand.NextInt(0, roofCount) : 0;
                lot.styleRoll = rand.NextFloat(0f, 1f);

                // Prefab replacement path: if the zone declares catalog categories
                // and the catalog actually has entries, tag the lot for prefab
                // placement instead of procedural geometry.
                lot.assetCategory = null;
                if (zone != null && zone.assetCategories != null && zone.assetCategories.Length > 0
                    && profile.catalog != null)
                {
                    var eligible = zone.assetCategories;
                    string pick = eligible[rand.NextInt(0, eligible.Length)];
                    if (profile.catalog.HasCategory(pick))
                        lot.assetCategory = pick;
                }

                lot.archetype = ResolveArchetype(profile.theme, zone, lot, rand);
            }
        }

        static BuildingArchetype ResolveArchetype(WorldTheme theme, ZoneProfile zone, LotData lot, DeterministicRandom rand)
        {
            // Theme is the architectural identity of an expansion scenario. Do
            // not make its signature buildings conditional on a zone reference:
            // profiles can be generated with missing/legacy zone assets, and a
            // theme must still read correctly at both small and large scales.
            switch (theme)
            {
                case WorldTheme.Railway:
                    return rand.Chance(0.48f) ? BuildingArchetype.Station : BuildingArchetype.RailDepot;
                case WorldTheme.Metro:
                    return rand.Chance(0.5f) ? BuildingArchetype.MetroStation : BuildingArchetype.MetroTower;
                case WorldTheme.Harbor:
                    float harborRoll = rand.NextFloat(0f, 1f);
                    return harborRoll < 0.46f ? BuildingArchetype.HarborWarehouse
                        : harborRoll < 0.76f ? BuildingArchetype.HarborSilo
                        : BuildingArchetype.Lighthouse;
                case WorldTheme.Airport:
                    float airportRoll = rand.NextFloat(0f, 1f);
                    return airportRoll < 0.46f ? BuildingArchetype.Hangar
                        : airportRoll < 0.79f ? BuildingArchetype.Terminal
                        : BuildingArchetype.ControlTower;
            }

            if (zone == null) return ResolveCityFallback(lot, rand);
            return ResolveCityArchetype(zone, lot, rand);
        }

        static BuildingArchetype ResolveCityFallback(LotData lot, DeterministicRandom rand)
        {
            float roll = rand.NextFloat(0f, 1f);
            if (roll < 0.42f) return BuildingArchetype.House;
            if (roll < 0.68f) return BuildingArchetype.Apartment;
            if (roll < 0.86f) return BuildingArchetype.Retail;
            return lot.rect.width > 24f ? BuildingArchetype.Office : BuildingArchetype.Warehouse;
        }

        static BuildingArchetype ResolveCityArchetype(ZoneProfile zone, LotData lot, DeterministicRandom rand)
        {
            switch (zone.usage)
            {
                case ZoneUsage.Residential:
                    // Deep lots become apartment slabs; shallow ones row houses.
                    float minSide = UnityEngine.Mathf.Min(lot.rect.width, lot.rect.height);
                    return minSide < 18f || rand.Chance(0.55f)
                        ? BuildingArchetype.House
                        : BuildingArchetype.Apartment;
                case ZoneUsage.Commercial:
                    return lot.rect.width > 24f && rand.Chance(0.7f)
                        ? BuildingArchetype.Retail
                        : BuildingArchetype.Apartment;
                case ZoneUsage.Office:
                    return rand.Chance(0.12f)
                        ? BuildingArchetype.ControlTower   // occasional landmark shaft
                        : BuildingArchetype.Office;
                case ZoneUsage.Industrial:
                    return rand.Chance(0.25f)
                        ? BuildingArchetype.Silo
                        : BuildingArchetype.Warehouse;
                case ZoneUsage.Park:
                    return BuildingArchetype.House;        // small pavilions in park blocks
                case ZoneUsage.Rail:
                    return rand.Chance(0.3f)
                        ? BuildingArchetype.Station
                        : BuildingArchetype.Warehouse;
                case ZoneUsage.Harbor:
                    return rand.Chance(0.3f)
                        ? BuildingArchetype.Silo
                        : BuildingArchetype.Warehouse;
                case ZoneUsage.Airport:
                    return rand.Chance(0.4f)
                        ? BuildingArchetype.Hangar
                        : BuildingArchetype.Terminal;
                case ZoneUsage.Metro:
                    return rand.Chance(0.5f) ? BuildingArchetype.MetroStation : BuildingArchetype.MetroTower;
                default:
                    return BuildingArchetype.House;
            }
        }
    }
}
