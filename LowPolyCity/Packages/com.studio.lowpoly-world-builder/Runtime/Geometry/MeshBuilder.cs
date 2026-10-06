using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace LowPolyWorldBuilder.Geometry
{
    /// <summary>
    /// Simple multi-submesh mesh accumulator. Submesh index corresponds to a
    /// material slot chosen by the caller. Uses 32-bit indices automatically
    /// when the vertex count exceeds 65535 (with a report hook).
    /// </summary>
    public sealed class MeshBuilder
    {
        readonly List<Vector3> _verts = new List<Vector3>();
        readonly List<Vector3> _normals = new List<Vector3>();
        readonly List<Vector2> _uvs = new List<Vector2>();
        readonly List<List<int>> _tris = new List<List<int>>();

        public int SubmeshCount => _tris.Count;
        public int VertexCount => _verts.Count;

        public int EnsureSubmesh(int index)
        {
            while (_tris.Count <= index) _tris.Add(new List<int>());
            return index;
        }

        public int AddVertex(Vector3 v, Vector3 n, Vector2 uv)
        {
            _verts.Add(v); _normals.Add(n); _uvs.Add(uv);
            return _verts.Count - 1;
        }

        public void AddTriangle(int submesh, int a, int b, int c)
        {
            EnsureSubmesh(submesh);
            _tris[submesh].Add(a); _tris[submesh].Add(b); _tris[submesh].Add(c);
        }

        /// <summary>Add an axis-aligned quad given 4 corners (CCW seen from the normal side).</summary>
        public void AddQuad(int submesh, Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 normal)
        {
            int i0 = AddVertex(a, normal, new Vector2(0, 0));
            int i1 = AddVertex(b, normal, new Vector2(1, 0));
            int i2 = AddVertex(c, normal, new Vector2(1, 1));
            int i3 = AddVertex(d, normal, new Vector2(0, 1));
            AddTriangle(submesh, i0, i1, i2);
            AddTriangle(submesh, i0, i2, i3);
        }

        /// <summary>Add a box. faces bitmask: 1=+X 2=-X 4=+Y 8=-Y 16=+Z 32=-Z.</summary>
        public void AddBox(int submesh, Vector3 center, Vector3 size, int faces = 0x3F)
        {
            Vector3 e = size * 0.5f;
            Vector3 p000 = center + new Vector3(-e.x, -e.y, -e.z);
            Vector3 p001 = center + new Vector3(-e.x, -e.y, e.z);
            Vector3 p010 = center + new Vector3(-e.x, e.y, -e.z);
            Vector3 p011 = center + new Vector3(-e.x, e.y, e.z);
            Vector3 p100 = center + new Vector3(e.x, -e.y, -e.z);
            Vector3 p101 = center + new Vector3(e.x, -e.y, e.z);
            Vector3 p110 = center + new Vector3(e.x, e.y, -e.z);
            Vector3 p111 = center + new Vector3(e.x, e.y, e.z);

            if ((faces & 1) != 0) AddQuad(submesh, p100, p101, p111, p110, Vector3.right);
            if ((faces & 2) != 0) AddQuad(submesh, p001, p000, p010, p011, Vector3.left);
            if ((faces & 4) != 0) AddQuad(submesh, p010, p110, p111, p011, Vector3.up);
            if ((faces & 8) != 0) AddQuad(submesh, p000, p001, p101, p100, Vector3.down);
            if ((faces & 16) != 0) AddQuad(submesh, p101, p001, p011, p111, Vector3.forward);
            if ((faces & 32) != 0) AddQuad(submesh, p000, p100, p110, p010, Vector3.back);
        }

        /// <summary>Upright prism (cartoon tree foliage, roofs).</summary>
        public void AddPyramid(int submesh, Vector3 baseCenter, float halfW, float height)
        {
            Vector3 b0 = baseCenter + new Vector3(-halfW, 0, -halfW);
            Vector3 b1 = baseCenter + new Vector3(halfW, 0, -halfW);
            Vector3 b2 = baseCenter + new Vector3(halfW, 0, halfW);
            Vector3 b3 = baseCenter + new Vector3(-halfW, 0, halfW);
            Vector3 apex = baseCenter + new Vector3(0, height, 0);
            AddTri(submesh, b0, b1, apex);
            AddTri(submesh, b1, b2, apex);
            AddTri(submesh, b2, b3, apex);
            AddTri(submesh, b3, b0, apex);
            // base
            AddTri(submesh, b2, b1, b0);
            AddTri(submesh, b3, b2, b0);
        }

        public void AddTri(int submesh, Vector3 a, Vector3 b, Vector3 c)
        {
            Vector3 n = Vector3.Cross(b - a, c - a).normalized;
            int i0 = AddVertex(a, n, Vector2.zero);
            int i1 = AddVertex(b, n, Vector2.right);
            int i2 = AddVertex(c, n, Vector2.up);
            AddTriangle(submesh, i0, i1, i2);
        }

        /// <summary>Cylinder (trunks, lamp posts), axis = +Y.</summary>
        public void AddCylinder(int submesh, Vector3 baseCenter, float radius, float height, int segments = 8)
        {
            for (int i = 0; i < segments; i++)
            {
                float a0 = (float)i / segments * Mathf.PI * 2f;
                float a1 = (float)(i + 1) / segments * Mathf.PI * 2f;
                Vector3 d0 = new Vector3(Mathf.Cos(a0), 0, Mathf.Sin(a0));
                Vector3 d1 = new Vector3(Mathf.Cos(a1), 0, Mathf.Sin(a1));
                Vector3 v0 = baseCenter + d0 * radius;
                Vector3 v1 = baseCenter + d1 * radius;
                Vector3 n = (d0 + d1).normalized;
                AddQuad(submesh, v0, v1, v1 + Vector3.up * height, v0 + Vector3.up * height, n);
                AddTri(submesh, baseCenter + Vector3.up * height, v0 + Vector3.up * height, v1 + Vector3.up * height);
            }
        }

        public Mesh Build(string name)
        {
            var mesh = new Mesh { name = name };
            if (_verts.Count > 65535)
                mesh.indexFormat = IndexFormat.UInt32;
            mesh.SetVertices(_verts);
            mesh.SetNormals(_normals);
            mesh.SetUVs(0, _uvs);
            mesh.subMeshCount = _tris.Count;
            for (int i = 0; i < _tris.Count; i++)
                mesh.SetTriangles(_tris[i], i);
            mesh.RecalculateBounds();
            return mesh;
        }
    }
}
