using System.Collections.Generic;
using LowPolyWorldBuilder.Data;
using LowPolyWorldBuilder.Geometry;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Turns a decoded <see cref="MapDocument"/> into scene content: one terrain mesh
    /// with a submesh per biome, a sea plane, and one GameObject per instance.
    ///
    /// Kept apart from SceneAssembler's BuildPlan path because the two inputs share
    /// nothing beyond "produces GameObjects" — this one is a tilemap plus instances,
    /// that one is roads, blocks and lots. SceneAssembler.FromJson delegates here so
    /// the public entry point stays in one place.
    /// </summary>
    public sealed class MapSceneBuilder
    {
        readonly MapDocument _doc;
        readonly MaterialFactory _mats;
        readonly List<Material> _biomeMaterials = new List<Material>();
        readonly Dictionary<int, int> _biomeToSubmesh = new Dictionary<int, int>();

        public int TerrainVertexCount { get; private set; }
        public int TerrainSubmeshCount => _biomeToSubmesh.Count;
        public int InstanceObjectCount { get; private set; }

        public MapSceneBuilder(MapDocument doc, MaterialFactory mats)
        {
            _doc = doc;
            _mats = mats;
        }

        public GameObject Build(Transform parent)
        {
            var root = new GameObject("Map_" + _doc.ThemeId);
            root.transform.SetParent(parent, false);
            BuildTerrain(root.transform);
            BuildSea(root.transform);

            var scatter = new GameObject("Scatter");
            scatter.transform.SetParent(root.transform, false);
            foreach (var inst in _doc.Instances)
                PlaceInstance(scatter.transform, inst);
            return root;
        }

        // ---- terrain ---------------------------------------------------------

        void BuildTerrain(Transform parent)
        {
            int w = _doc.Width, h = _doc.Height;
            float cell = (float)_doc.TileSizeMeters;

            var verts = new List<Vector3>(w * h);
            var uvs = new List<Vector2>(w * h);
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    verts.Add(new Vector3(x * cell, _doc.WorldY(_doc.HeightAt(x, y)), y * cell));
                    uvs.Add(new Vector2(x / (float)w, y / (float)h));
                }
            }
            TerrainVertexCount = verts.Count;

            // Triangles are bucketed per biome so every biome can carry its own colour
            // straight from biome_legend, under any render pipeline.
            var buckets = new List<List<int>>();
            for (int y = 0; y < h - 1; y++)
            {
                for (int x = 0; x < w - 1; x++)
                {
                    int biome = _doc.BiomeAt(x, y);
                    if (!_biomeToSubmesh.TryGetValue(biome, out int slot))
                    {
                        slot = buckets.Count;
                        _biomeToSubmesh[biome] = slot;
                        buckets.Add(new List<int>());
                        var def = _doc.BiomeById(biome);
                        var col = def != null ? ToColor(def.ColorRgb) : Color.magenta;
                        _biomeMaterials.Add(_mats.Get(
                            "map_" + (def != null ? def.Key : biome.ToString()), col));
                    }
                    var tris = buckets[slot];
                    int i0 = y * w + x, i1 = i0 + 1, i2 = i0 + w, i3 = i2 + 1;
                    // Alternate the diagonal so the tessellation has no directional bias.
                    if (((x + y) & 1) == 0)
                    {
                        tris.Add(i0); tris.Add(i2); tris.Add(i1);
                        tris.Add(i1); tris.Add(i2); tris.Add(i3);
                    }
                    else
                    {
                        tris.Add(i0); tris.Add(i2); tris.Add(i3);
                        tris.Add(i0); tris.Add(i3); tris.Add(i1);
                    }
                }
            }

            var mesh = new Mesh { name = "LPW_MapTerrain" };
            if (verts.Count > 65535) mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            mesh.SetVertices(verts);
            mesh.SetUVs(0, uvs);
            mesh.subMeshCount = buckets.Count;
            for (int i = 0; i < buckets.Count; i++) mesh.SetTriangles(buckets[i], i);
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();

            var go = new GameObject("Terrain");
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            go.AddComponent<MeshRenderer>().sharedMaterials = _biomeMaterials.ToArray();
        }

        void BuildSea(Transform parent)
        {
            if (_doc.SeaLevelNorm <= 0) return;
            float w = _doc.Width * (float)_doc.TileSizeMeters;
            float d = _doc.Height * (float)_doc.TileSizeMeters;
            float y = _doc.WorldY((float)_doc.SeaLevelNorm);

            var mb = new MeshBuilder();
            mb.AddQuad(0, new Vector3(0, y, 0), new Vector3(0, y, d),
                new Vector3(w, y, d), new Vector3(w, y, 0), Vector3.up);

            MapBiome water = null;
            foreach (var b in _doc.Legend)
                if (b.IsWater) { water = b; break; }
            var col = water != null ? ToColor(water.ColorRgb) : new Color(0.1f, 0.3f, 0.5f, 0.75f);

            var go = new GameObject("Sea");
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mb.Build("LPW_MapSea");
            go.AddComponent<MeshRenderer>().sharedMaterials = new[] { _mats.Get("map_sea", col) };
        }

        // ---- instances -------------------------------------------------------

        void PlaceInstance(Transform parent, MapInstance inst)
        {
            var go = new GameObject($"{inst.Category}_{inst.Id}_{inst.Type}");
            go.transform.SetParent(parent, false);
            go.transform.position = new Vector3(
                (float)inst.World[0], (float)inst.World[1], (float)inst.World[2]);
            go.transform.rotation = Quaternion.Euler(0f, (float)inst.RotationDegrees, 0f);
            float s = (float)inst.Scale;
            go.transform.localScale = new Vector3(s, s, s);

            var mb = new MeshBuilder();
            Material[] mats;
            switch (inst.Type)
            {
                case "pine_snow_sparse":
                case "pine_snow_dense":
                case "tree_broadleaf":
                case "tree_forest":
                    mb.AddCylinder(0, Vector3.zero, 0.22f, 1.4f, 6);
                    mb.AddPyramid(1, new Vector3(0, 1.1f, 0), 1.1f, 2.6f);
                    mats = _mats.TreeMats();
                    break;
                case "tree_palm":
                    mb.AddCylinder(0, Vector3.zero, 0.18f, 2.2f, 6);
                    mb.AddPyramid(1, new Vector3(0, 2.0f, 0), 1.3f, 1.1f);
                    mats = _mats.TreeMats();
                    break;
                case "birch_snow_dead":
                    mb.AddCylinder(0, Vector3.zero, 0.16f, 2.0f, 5);
                    mats = new[] { _mats.Trunk() };
                    break;
                case "ice_boulder":
                case "rock":
                    mb.AddBox(0, new Vector3(0, 0.35f, 0), new Vector3(1.1f, 0.7f, 1.1f));
                    mats = new[] { _mats.Accent() };
                    break;
                case "snow_drift":
                    mb.AddBox(0, new Vector3(0, 0.18f, 0), new Vector3(1.6f, 0.36f, 1.6f));
                    mats = new[] { _mats.Ground() };
                    break;
                case "frozen_reed":
                case "grass_tuft":
                    mb.AddBox(0, new Vector3(0, 0.25f, 0), new Vector3(0.7f, 0.5f, 0.7f));
                    mats = new[] { _mats.Foliage() };
                    break;
                case "reed":
                    mb.AddCylinder(0, Vector3.zero, 0.25f, 0.9f, 5);
                    mats = new[] { _mats.Foliage() };
                    break;
                default:
                    mb.AddBox(0, new Vector3(0, 0.3f, 0), new Vector3(0.8f, 0.6f, 0.8f));
                    mats = new[] { _mats.Accent() };
                    break;
            }
            go.AddComponent<MeshFilter>().sharedMesh = mb.Build("LPW_Inst_" + inst.Type);
            go.AddComponent<MeshRenderer>().sharedMaterials = mats;
            InstanceObjectCount++;
        }

        static Color ToColor(uint rgb) => new Color(
            ((rgb >> 16) & 0xFF) / 255f,
            ((rgb >> 8) & 0xFF) / 255f,
            (rgb & 0xFF) / 255f,
            1f);
    }
}
