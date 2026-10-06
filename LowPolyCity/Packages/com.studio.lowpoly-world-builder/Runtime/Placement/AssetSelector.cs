using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Generation;

namespace LowPolyWorldBuilder.Placement
{
    /// <summary>
    /// Deterministically picks a catalog entry for a lot/scatter category,
    /// filtered by footprint fit and variant tags.
    /// </summary>
    public sealed class AssetSelector
    {
        public AssetTemplateEntry Select(AssetCatalog catalog, string category,
                                         float maxFootprintX, float maxFootprintZ,
                                         DeterministicRandom rand)
        {
            if (catalog == null || string.IsNullOrEmpty(category)) return null;
            var candidates = catalog.ByCategory(category);
            if (candidates.Count == 0) return null;

            var weights = new float[candidates.Count];
            for (int i = 0; i < candidates.Count; i++)
            {
                var e = candidates[i];
                bool fits = e.size.x <= maxFootprintX * 1.2f && e.size.z <= maxFootprintZ * 1.2f;
                weights[i] = fits ? e.weight : 0f;
            }
            int pick = rand.WeightedPick(weights);
            return pick < 0 ? null : candidates[pick];
        }
    }
}
