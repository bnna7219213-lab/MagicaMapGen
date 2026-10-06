using System;
using System.Collections.Generic;
using UnityEngine;

namespace LowPolyWorldBuilder.Data
{
    public enum RoadNodeKind { Corner, TJunction, Cross, Endpoint }

    [Serializable]
    public sealed class RoadNode
    {
        public Vector2Int grid;        // lattice coordinate
        public Vector3 position;       // world position (y = 0)
        public List<int> edges = new List<int>();

        public RoadNodeKind Kind
        {
            get
            {
                switch (edges.Count)
                {
                    case 1: return RoadNodeKind.Endpoint;
                    case 2: return RoadNodeKind.Corner;
                    case 3: return RoadNodeKind.TJunction;
                    default: return RoadNodeKind.Cross;
                }
            }
        }
    }

    [Serializable]
    public sealed class RoadEdge
    {
        public int a, b;               // node indices
        public float width;
        public bool active = true;     // future: rail/metro reuse this graph with a 'mode' flag
        public float Length(Vector3 pa, Vector3 pb) => Vector3.Distance(pa, pb);
    }

    /// <summary>
    /// Pure-data road network. First version is a parametric grid; the same
    /// graph abstraction later carries rail/metro/monorail edges (plan 5.2).
    /// </summary>
    [Serializable]
    public sealed class RoadGraph
    {
        public List<RoadNode> nodes = new List<RoadNode>();
        public List<RoadEdge> edges = new List<RoadEdge>();

        public int AddNode(Vector2Int grid, Vector3 pos)
        {
            nodes.Add(new RoadNode { grid = grid, position = pos });
            return nodes.Count - 1;
        }

        public int AddEdge(int a, int b, float width)
        {
            edges.Add(new RoadEdge { a = a, b = b, width = width });
            int idx = edges.Count - 1;
            nodes[a].edges.Add(idx);
            nodes[b].edges.Add(idx);
            return idx;
        }

        /// <summary>Connectivity check: every active edge reachable from edge 0.</summary>
        public bool IsConnected(out int orphanCount)
        {
            orphanCount = 0;
            if (edges.Count == 0) return true;
            var seen = new HashSet<int>();
            var stack = new Stack<int>();
            stack.Push(edges[0].a);
            while (stack.Count > 0)
            {
                int n = stack.Pop();
                if (!seen.Add(n)) continue;
                foreach (var ei in nodes[n].edges)
                {
                    var e = edges[ei];
                    if (!e.active) continue;
                    stack.Push(e.a == n ? e.b : e.a);
                }
            }
            foreach (var n in nodes)
                if (n.edges.Count > 0 && !seen.Contains(nodes.IndexOf(n)))
                    orphanCount++;
            return orphanCount == 0;
        }
    }
}
