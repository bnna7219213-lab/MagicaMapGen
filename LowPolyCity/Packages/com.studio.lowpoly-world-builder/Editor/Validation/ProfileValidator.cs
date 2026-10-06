using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Validation
{
    /// <summary>Checks profile parameter ranges before any generation starts.</summary>
    public static class ProfileValidator
    {
        public static bool Validate(WorldBuildProfile profile, WorldBuildReport report)
        {
            bool ok = true;
            if (profile == null)
            {
                report.Error("Validate", "No WorldBuildProfile assigned");
                return false;
            }
            if (profile.blockCount.x < 1 || profile.blockCount.y < 1)
            { report.Error("Validate", "blockCount must be >= 1x1"); ok = false; }
            if (profile.blockCount.x * profile.blockCount.y > 256)
                report.Warn("Validate", "More than 256 blocks: consider chunked generation (phase 7)");
            if (profile.blockSize < 10f)
            { report.Error("Validate", "blockSize too small (< 10m)"); ok = false; }
            if (profile.roadWidth < 2f)
            { report.Error("Validate", "roadWidth too small (< 2m)"); ok = false; }
            if (profile.minBuildingHeight <= 0f || profile.maxBuildingHeight < profile.minBuildingHeight)
            { report.Error("Validate", "Invalid building height range"); ok = false; }
            if (profile.palette == null)
                report.Warn("Validate", "No StylePalette assigned: gray fallback materials will be used");

            // Fix C3: Validate zones so we never silently skip zone assignment.
            if (profile.zones != null && profile.zones.Length > 0)
            {
                int nullCount = 0;
                float totalWeight = 0f;
                foreach (var z in profile.zones)
                {
                    if (z == null) { nullCount++; continue; }
                    totalWeight += z.spawnWeight;
                }
                if (nullCount > 0)
                {
                    report.Error("Validate", $"profile.zones has {nullCount} null entries — assignments will fail");
                    ok = false;
                }
                if (totalWeight <= 0f)
                {
                    report.Error("Validate", "profile.zones all have spawnWeight <= 0 — zone pick will always fail");
                    ok = false;
                }
            }

            return ok;
        }
    }
}
