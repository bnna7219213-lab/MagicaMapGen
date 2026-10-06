using System;
using System.Collections.Generic;
using LowPolyWorldBuilder.Config;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Generation;
using LowPolyWorldBuilder.Geometry;
using LowPolyWorldBuilder.Placement;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Turns a BuildPlan into scene GameObjects under the marked root node.
    /// Per-block grouping keeps rebuild granularity and selection easy.
    /// </summary>
    public sealed class SceneAssembler
    {
        readonly BuildingMeshBuilder _buildingMesh = new BuildingMeshBuilder();
        readonly RoadMeshBuilder _roadMesh = new RoadMeshBuilder();
        readonly AssetSelector _selector = new AssetSelector();

        public GameObject Assemble(WorldBuildProfile profile, BuildPlan plan, string profileGuid,
                                   WorldBuildReport report, bool registerUndo)
        {
            var matFactory = new MaterialFactory(profile.palette != null ? profile.palette : ScriptableObject.CreateInstance<StylePalette>());
            var root = GeneratedRootManager.FindOrCreateRoot(profileGuid, plan.seed, "world", true, out _);
            int removed = GeneratedRootManager.ClearGeneratedChildren(root);
            if (removed > 0) report.Info("Assemble", $"Cleared {removed} previously generated children");

            AssembleRoads(profile, plan, root.transform, matFactory);
            AssembleBlocks(profile, plan, root.transform, matFactory, report);
            AssembleScatter(profile, plan, root.transform, matFactory, report);
            new ThemedInfrastructureAssembler().Assemble(profile, plan, root.transform, matFactory);

            report.assetReferences.Add("profile:" + profileGuid);
            return root;
        }

        /// <summary>
        /// Build the scene directly from a mapgen <c>*_map.json</c>.
        ///
        /// This is the path-B entry point: the generator owns world creation and this
        /// package only consumes the result. The map is therefore treated as the
        /// source of truth rather than regenerated from a WorldBuildProfile — there is
        /// no profile to honour, and pretending otherwise would silently discard the
        /// generator's terrain, biome and scatter decisions.
        ///
        /// Reuses the same root-node and lock-preserving cleanup as the BuildPlan path,
        /// so a manual lock taken on imported content survives a re-import.
        /// </summary>
        public GameObject FromJson(MapDocument doc, string sourceLabel, WorldBuildReport report)
        {
            if (doc == null) throw new ArgumentNullException(nameof(doc));
            var palette = ScriptableObject.CreateInstance<StylePalette>();
            var matFactory = new MaterialFactory(palette);

            // Region key includes the label so two imported maps never share a root.
            string regionKey = "map_" + (string.IsNullOrEmpty(sourceLabel) ? doc.Label : sourceLabel);
            var root = GeneratedRootManager.FindOrCreateRoot("json:" + doc.ThemeId, doc.Seed, regionKey, true, out _);
            int removed = GeneratedRootManager.ClearGeneratedChildren(root);
            if (removed > 0) report.Info("FromJson", $"Cleared {removed} previously generated children");

            var builder = new MapSceneBuilder(doc, matFactory);
            var mapRoot = builder.Build(root.transform);

            report.seed = doc.Seed;
            report.profileName = sourceLabel;
            report.theme = doc.ThemeId;
            report.gridWidth = doc.Width;
            report.gridHeight = doc.Height;
            report.scatterCount = doc.Instances.Count;
            report.buildingCount = 0;
            report.blockCount = 0;
            report.lotCount = 0;
            report.roadSegmentCount = 0;
            report.Info("FromJson", $"schema v{doc.SchemaVersion} from {doc.GeneratorVersion}, " +
                                    $"height source '{doc.HeightSource}', " +
                                    $"{builder.TerrainVertexCount} terrain verts, " +
                                    $"{builder.TerrainSubmeshCount} biome submeshes, " +
                                    $"{builder.InstanceObjectCount} instance objects");
            if (!doc.ContractPassed)
                report.Warn("FromJson", "generator contract was NOT satisfied for this map; " +
                                        "the scene may violate the theme's guarantees");
            foreach (var w in doc.Warnings) report.Warn("FromJson", w);

            report.assetReferences.Add("mapjson:" + sourceLabel);
            mapRoot.name = "Map_" + doc.ThemeId + "_" + doc.Label;
            return root;
        }

        void AssembleRoads(WorldBuildProfile profile, BuildPlan plan, Transform parent, MaterialFactory mats)
        {
            var go = new GameObject("Roads");
            go.transform.SetParent(parent, false);
            var mesh = _roadMesh.Build(plan.roadGraph, profile.sidewalkWidth,
                profile.WorldSizeX, profile.WorldSizeZ, plan.blocks, "LPW_Roads");
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            go.AddComponent<MeshRenderer>().sharedMaterials = mats.RoadMats();
        }

        void AssembleBlocks(WorldBuildProfile profile, BuildPlan plan, Transform parent,
                            MaterialFactory mats, WorldBuildReport report)
        {
            // Fix C4: ClearGeneratedChildren now preserves the Blocks container only
            // when it holds a locked block (and keeps just the locked blocks inside).
            // Reuse that surviving container instead of adding a second one, and skip
            // regenerating any block the user locked so preserved geometry is not
            // duplicated. With no locks the container was fully cleared, so this
            // creates a fresh one exactly as before.
            var existing = parent.Find("Blocks");
            GameObject blocksRoot;
            if (existing != null)
            {
                blocksRoot = existing.gameObject;
            }
            else
            {
                blocksRoot = new GameObject("Blocks");
                blocksRoot.transform.SetParent(parent, false);
                var blocksMarker = blocksRoot.AddComponent<WorldBuildMarker>();
                blocksMarker.profileGuid = report.assetReferences.Count > 0 ? report.assetReferences[0].Replace("profile:", "") : "";
                blocksMarker.seed = plan.seed;
                blocksMarker.regionKey = "Blocks";
            }

            foreach (var block in plan.blocks)
            {
                // A block that survived cleanup is one the user locked; keep it as-is.
                var preserved = blocksRoot.transform.Find(block.RegionKey);
                if (preserved != null)
                {
                    var pm = preserved.GetComponent<WorldBuildMarker>();
                    if (pm != null && pm.manualLock) continue;
                }

                var blockGo = new GameObject(block.RegionKey);
                blockGo.transform.SetParent(blocksRoot.transform, false);
                var marker = blockGo.AddComponent<WorldBuildMarker>();
                marker.seed = plan.seed;
                marker.regionKey = block.RegionKey;

                var rand = new DeterministicRandom(
                    GenerationContext.HashSeed(plan.seed, block.RegionKey + "/place"));

                if (block.infrastructureBlock) continue;
                foreach (var lot in block.lots)
                {
                    if (!string.IsNullOrEmpty(lot.assetCategory))
                    {
                        if (TryPlacePrefab(profile, lot, blockGo.transform, rand, report))
                            continue; // prefab placed instead of procedural mesh
                    }

                    var mesh = _buildingMesh.Build(lot, "LPW_Building");
                    var go = new GameObject($"b_{lot.rect.xMin:F0}_{lot.rect.yMin:F0}");
                    go.transform.SetParent(blockGo.transform, false);
                    go.transform.position = PlacementRules.LotCenter(lot);
                    go.transform.rotation = PlacementRules.FacingRotation(lot.facing);
                    go.AddComponent<MeshFilter>().sharedMesh = mesh;
                    go.AddComponent<MeshRenderer>().sharedMaterials =
                        mats.BuildingMats(lot.wallColorIndex, lot.roofColorIndex);
                }
            }
        }

        bool TryPlacePrefab(WorldBuildProfile profile, LotData lot, Transform parent,
                            DeterministicRandom rand, WorldBuildReport report)
        {
            var entry = _selector.Select(profile.catalog, lot.assetCategory,
                lot.rect.width, lot.rect.height, rand);
            if (entry == null)
            {
                report.Warn("Prefab", $"No catalog entry fits category '{lot.assetCategory}', using procedural fallback");
                return false;
            }
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(entry.prefab);
            instance.transform.SetParent(parent, false);
            instance.transform.position = PlacementRules.LotCenter(lot);
            instance.transform.rotation = PlacementRules.FacingRotation(lot.facing);
            float variation = entry.allowScaleVariation ? rand.NextFloat(0.9f, 1.1f) : 1f;
            float s = PlacementRules.FitScale(entry.size, lot.rect, entry.allowScaleVariation, variation);
            instance.transform.localScale = new Vector3(s, s, s);
            report.prefabInstanceCount++;
            report.assetReferences.Add(AssetDatabase.GetAssetPath(entry.prefab));
            return true;
        }

        void AssembleScatter(WorldBuildProfile profile, BuildPlan plan, Transform parent,
                             MaterialFactory mats, WorldBuildReport report)
        {
            var root = new GameObject("Scatter");
            root.transform.SetParent(parent, false);

            foreach (var item in plan.scatter)
            {
                // Prefer user prefab templates; fall back to procedural props.
                var rand = new DeterministicRandom(GenerationContext.HashSeed(
                    plan.seed, "scatter_" + item.position.GetHashCode()));
                var entry = _selector.Select(profile.catalog, item.category, 4f, 4f, rand);
                if (entry != null)
                {
                    var inst = (GameObject)PrefabUtility.InstantiatePrefab(entry.prefab);
                    inst.transform.SetParent(root.transform, false);
                    inst.transform.position = item.position;
                    inst.transform.rotation = Quaternion.Euler(0, item.rotationY, 0);
                    inst.transform.localScale = Vector3.one * item.scale;
                    report.prefabInstanceCount++;
                    continue;
                }

                var go = item.category == "prop.lamp"
                    ? BuildLamp(mats)
                    : item.category == "prop.tank"
                        ? BuildTank(mats)
                        : item.category == "prop.pole"
                            ? BuildPole(mats)
                            : BuildTree(mats);
                go.transform.SetParent(root.transform, false);
                go.transform.position = item.position;
                go.transform.rotation = Quaternion.Euler(0, item.rotationY, 0);
                go.transform.localScale = Vector3.one * item.scale;
            }
        }

        static GameObject BuildTree(MaterialFactory mats)
        {
            var mb = new MeshBuilder();
            mb.AddCylinder(0, new Vector3(0, 0, 0), 0.25f, 1.6f, 6);
            mb.AddPyramid(1, new Vector3(0, 1.2f, 0), 1.5f, 3.2f);
            var go = new GameObject("tree");
            go.AddComponent<MeshFilter>().sharedMesh = mb.Build("LPW_Tree");
            go.AddComponent<MeshRenderer>().sharedMaterials = mats.TreeMats();
            return go;
        }

        static GameObject BuildLamp(MaterialFactory mats)
        {
            var mb = new MeshBuilder();
            mb.AddCylinder(0, new Vector3(0, 0, 0), 0.08f, 4.5f, 6);
            mb.AddBox(0, new Vector3(0, 4.6f, 0), new Vector3(0.5f, 0.25f, 0.5f));
            var go = new GameObject("lamp");
            go.AddComponent<MeshFilter>().sharedMesh = mb.Build("LPW_Lamp");
            go.AddComponent<MeshRenderer>().sharedMaterials = mats.LampMats();
            return go;
        }

        static GameObject BuildTank(MaterialFactory mats)
        {
            var mb = new MeshBuilder();
            mb.AddCylinder(0, new Vector3(0, 0, 0), 1.1f, 2.6f, 10);
            mb.AddPyramid(1, new Vector3(0, 2.6f, 0), 1.1f, 0.7f);
            var go = new GameObject("tank");
            go.AddComponent<MeshFilter>().sharedMesh = mb.Build("LPW_Tank");
            go.AddComponent<MeshRenderer>().sharedMaterials = new[] { mats.Accent(), mats.Roof(0) };
            return go;
        }

        static GameObject BuildPole(MaterialFactory mats)
        {
            var mb = new MeshBuilder();
            mb.AddCylinder(0, new Vector3(0, 0, 0), 0.12f, 6.5f, 6);
            mb.AddBox(1, new Vector3(0, 6.1f, 0), new Vector3(2.4f, 0.14f, 0.14f));
            var go = new GameObject("utility_pole");
            go.AddComponent<MeshFilter>().sharedMesh = mb.Build("LPW_Pole");
            go.AddComponent<MeshRenderer>().sharedMaterials = new[] { mats.Trunk(), mats.Lamp() };
            return go;
        }
    }
}
