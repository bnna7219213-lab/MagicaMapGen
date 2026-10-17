using System.Collections.Generic;
using System.Globalization;
using System.Text;
using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Diff the live scene against a source <see cref="MapDocument"/> and emit a
    /// mapgen <c>edits.json</c> (delete / move / add). This is the Unity half of the
    /// phase-3 round-trip: a designer edits tagged objects in the scene, the differ
    /// records exactly those changes, and <see cref="OverlayReceiver"/> replays them
    /// through <c>mapgen --overlay</c>. Relies on <see cref="MapInstanceId"/> tags the
    /// builder placed on every instantiated object.
    /// </summary>
    public sealed class SceneDiffer
    {
        readonly CultureInfo _inv = CultureInfo.InvariantCulture;

        /// <summary>
        /// Invert the artifact's world placement: world_x = (cellX + 0.5) * tile,
        /// world_z = (cellY + 0.5) * tile. Pure and independent of any scene state so
        /// the round-trip can be reasoned about -- and tested -- on its own.
        /// </summary>
        public static void WorldToCell(Vector3 world, double tile, out int x, out int y)
        {
            x = Mathf.RoundToInt((float)(world.x / tile) - 0.5f);
            y = Mathf.RoundToInt((float)(world.z / tile) - 0.5f);
        }

        public int DeleteCount { get; private set; }
        public int MoveCount { get; private set; }
        public int AddCount { get; private set; }
        /// <summary>Edits reoriented/re-scaled, each expressed as one delete + one add.</summary>
        public int RotateCount { get; private set; }

        /// <summary>
        /// Produce the edits.json document for the diff. <paramref name="moveEpsilonMeters"/>
        /// is the world-space distance beyond which a repositioned object counts as a move;
        /// <paramref name="rotEpsilonDegrees"/> / <paramref name="scaleEpsilon"/> do the same
        /// for rotation / scale (which have no dedicated mapgen op, so they become delete+add).
        /// </summary>
        public string BuildEditsJson(MapDocument doc, GameObject mapRoot,
                                     float moveEpsilonMeters = 0.01f,
                                     float rotEpsilonDegrees = 0.5f,
                                     float scaleEpsilon = 0.01f)
        {
            DeleteCount = MoveCount = AddCount = RotateCount = 0;
            double tile = doc.TileSizeMeters;

            // Map scene objects back to their artifact ids; anything with Id < 0 that is
            // tagged user-added is a designer-created object to be emitted as an add.
            var byId = new Dictionary<int, MapInstanceId>();
            var manual = new List<MapInstanceId>();
            if (mapRoot != null)
            {
                foreach (var t in mapRoot.GetComponentsInChildren<MapInstanceId>(true))
                {
                    if (t.Id >= 0) byId[t.Id] = t;
                    else if (t.Source == "user-added") manual.Add(t);
                }
            }

            var sb = new StringBuilder();
            sb.Append("{\"schema_version\": 1, \"ops\": [");
            bool first = true;
            void Emit(string op)
            {
                if (!first) sb.Append(',');
                first = false;
                sb.Append(op);
            }

            foreach (var inst in doc.Instances)
            {
                if (inst.Source == "user-added" || inst.Source == "user-moved")
                    continue;   // hand-created objects are not diffed for delete here
                if (!byId.TryGetValue(inst.Id, out var tag))
                {
                    Emit("{\"op\":\"delete\",\"id\":" + inst.Id + "}");
                    DeleteCount++;
                    continue;
                }
                Vector3 tpos = tag.transform.position;
                WorldToCell(tpos, tile, out int cx, out int cy);
                bool moved = Vector3.Distance(tpos, tag.SpawnedWorld) > moveEpsilonMeters;
                float curRotY = tag.transform.rotation.eulerAngles.y;
                float rotDelta = Mathf.Abs(Mathf.DeltaAngle((float)tag.RotationDegrees, curRotY));
                float curScale = tag.transform.localScale.x;
                bool reoriented = Mathf.Abs(rotDelta) > rotEpsilonDegrees
                                  || Mathf.Abs(curScale - (float)tag.Scale) > scaleEpsilon;
                if (reoriented)
                {
                    // mapgen has no "set rotation/scale" op; express it as delete + add
                    // (documented in path_b_baseline.md 4.3), preserving the cell and the
                    // new orientation/scale. Takes precedence over a bare move.
                    Emit("{\"op\":\"delete\",\"id\":" + inst.Id + "}");
                    Emit("{\"op\":\"add\",\"cat\":\"" + JsonEscape(tag.Category) + "\",\"type\":\""
                         + JsonEscape(tag.Type) + "\",\"x\":" + cx + ",\"y\":" + cy
                         + ",\"scale\":" + curScale.ToString("0.####", _inv)
                         + ",\"rot\":" + curRotY.ToString("0.####", _inv) + "}");
                    DeleteCount++; AddCount++; RotateCount++;
                }
                else if (moved)
                {
                    Emit("{\"op\":\"move\",\"id\":" + inst.Id
                         + ",\"x\":" + cx + ",\"y\":" + cy + "}");
                    MoveCount++;
                }
            }

            foreach (var t in manual)
            {
                WorldToCell(t.transform.position, tile, out int cx, out int cy);
                Emit("{\"op\":\"add\",\"cat\":\"" + JsonEscape(t.Category) + "\",\"type\":\""
                     + JsonEscape(t.Type) + "\",\"x\":" + cx + ",\"y\":" + cy
                     + ",\"scale\":" + t.Scale.ToString("0.####", _inv)
                     + ",\"rot\":" + t.RotationDegrees.ToString("0.####", _inv) + "}");
                AddCount++;
            }

            sb.Append("]}");
            return sb.ToString();
        }

        static string JsonEscape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
