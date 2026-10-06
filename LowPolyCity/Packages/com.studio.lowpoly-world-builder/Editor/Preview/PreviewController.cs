using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Generation;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Preview
{
    /// <summary>
    /// Lightweight proxy preview: wireframe boxes for lots and line strips for
    /// roads under a temporary root (name-based, NOT marked — cleanup never
    /// confuses it with real generated content). No assets are saved.
    /// </summary>
    public sealed class PreviewController
    {
        public const string PreviewRootName = "LPW_Preview";
        public BuildPlan LastPlan { get; private set; }

        public BuildPlan ShowPreview(WorldBuildProfile profile)
        {
            Clear();
            var report = new WorldBuildReport { seed = profile.seed, profileName = profile.name };
            var plan = new WorldPlanGenerator().Generate(profile, report);
            LastPlan = plan;

            var root = new GameObject(PreviewRootName);
            foreach (var block in plan.blocks)
            {
                var bgo = new GameObject(block.RegionKey);
                bgo.transform.SetParent(root.transform, false);
                foreach (var lot in block.lots)
                {
                    var proxy = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    proxy.name = "lot";
                    Object.DestroyImmediate(proxy.GetComponent<Collider>());
                    proxy.transform.SetParent(bgo.transform, false);
                    proxy.transform.position = new Vector3(lot.rect.center.x, lot.height * 0.5f, lot.rect.center.y);
                    proxy.transform.localScale = new Vector3(lot.rect.width * 0.9f, lot.height, lot.rect.height * 0.9f);
                }
            }
            SceneView.RepaintAll();
            return plan;
        }

        public void Clear()
        {
            var existing = GameObject.Find(PreviewRootName);
            if (existing != null) Object.DestroyImmediate(existing);
            LastPlan = null;
        }
    }
}
