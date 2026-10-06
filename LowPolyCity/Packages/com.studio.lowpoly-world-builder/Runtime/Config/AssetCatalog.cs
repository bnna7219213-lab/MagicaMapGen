using System;
using System.Collections.Generic;
using UnityEngine;

namespace LowPolyWorldBuilder.Config
{
    [Serializable]
    public sealed class AssetTemplateEntry
    {
        public GameObject prefab;
        [Tooltip("Category key, e.g. 'building.house', 'vehicle.train', 'prop.tree'.")]
        public string category = "building.house";
        [Tooltip("Approximate footprint (X,Z) and height (Y) in meters.")]
        public Vector3 size = new Vector3(10f, 10f, 10f);
        [Range(0f, 100f)] public float weight = 1f;
        [Tooltip("Optional tags for variant filtering, e.g. 'corner','lowrise'.")]
        public string[] variantTags = new string[0];
        [Tooltip("Connection port names this prefab exposes (rail head, dock edge, gate...).")]
        public string[] ports = new string[0];
        public bool allowScaleVariation = true;
    }

    /// <summary>
    /// Directory of user-supplied prefab templates. Complex semantic assets
    /// (trains, planes, vehicles) enter the world only through this catalog.
    /// </summary>
    [CreateAssetMenu(menuName = "LowPolyWorld/Asset Catalog", fileName = "AssetCatalog")]
    public sealed class AssetCatalog : ScriptableObject
    {
        public List<AssetTemplateEntry> entries = new List<AssetTemplateEntry>();

        public List<AssetTemplateEntry> ByCategory(string category)
        {
            var list = new List<AssetTemplateEntry>();
            foreach (var e in entries)
                if (e != null && e.prefab != null && string.Equals(e.category, category, StringComparison.OrdinalIgnoreCase))
                    list.Add(e);
            return list;
        }

        public bool HasCategory(string category) => ByCategory(category).Count > 0;
    }
}
