using System.Collections.Generic;
using UnityEngine;

namespace LowPolyWorldBuilder.Geometry
{
    /// <summary>
    /// Groups generated meshes into budget-sized chunks so very large worlds
    /// can merge per-block or per-tile without rebuilding everything
    /// (plan 5.2 "large scene organization").
    /// </summary>
    public sealed class MeshChunk
    {
        public string key;
        public readonly List<Mesh> meshes = new List<Mesh>();
        public readonly List<Matrix4x4> transforms = new List<Matrix4x4>();
        public readonly List<Material[]> materials = new List<Material[]>();

        public void Add(Mesh mesh, Matrix4x4 trs, Material[] mats)
        {
            meshes.Add(mesh);
            transforms.Add(trs);
            materials.Add(mats);
        }
    }
}
