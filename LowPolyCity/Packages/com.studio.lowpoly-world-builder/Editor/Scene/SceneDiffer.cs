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

        /// <summary>
        /// Produce the edits.json document for the diff. <paramref name="moveEpsilonMeters"/>
        /// is the world-space distance beyond which a repositioned object counts as a move.
        /// </summary>
        public string BuildEditsJson(MapDocument doc, GameObject mapRoot,
                                     float moveEpsilonMeters = 0.01f)
        {
            DeleteCount = MoveCount = AddCount = 0;
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

            foreach (var inst in doc.Instances)
            {
                if (inst.Source == "user-added" || inst.Source == "user-moved")
                    continue;   // hand-created objects are not diffed for delete here
                if (!byId.TryGetValue(inst.Id, out var tag))
                {
                    if (!first) sb.Append(','); first = false;
                    sb.Append("{\"op\":\"delete\",\"id\":").Append(inst.Id).Append('}');
                    DeleteCount++;
                    continue;
                }
                if (Vector3.Distance(tag.transform.position, tag.SpawnedWorld) > moveEpsilonMeters)
                {
                    WorldToCell(tag.transform.position, tile, out int cx, out int cy);
                    if (!first) sb.Append(','); first = false;
                    sb.Append("{\"op\":\"move\",\"id\":").Append(inst.Id)
                      .Append(",\"x\":").Append(cx).Append(",\"y\":").Append(cy).Append('}');
                    MoveCount++;
                }
            }

            foreach (var t in manual)
            {
                WorldToCell(t.transform.position, tile, out int cx, out int cy);
                if (!first) sb.Append(','); first = false;
                sb.Append("{\"op\":\"add\",\"cat\":\"").Append(JsonEscape(t.Category))
                  .Append("\",\"type\":\"").Append(JsonEscape(t.Type))
                  .Append("\",\"x\":").Append(cx).Append(",\"y\":").Append(cy)
                  .Append(",\"scale\":").Append(t.Scale.ToString("0.####", _inv))
                  .Append(",\"rot\":").Append(t.RotationDegrees.ToString("0.####", _inv))
                  .Append('}');
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
