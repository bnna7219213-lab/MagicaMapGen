using LowPolyWorldBuilder.Data;
using UnityEditor;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Preview
{
    /// <summary>
    /// Scene-view helper: outlines generated roots and highlights manually
    /// locked regions so users see what a rebuild will preserve.
    /// </summary>
    public static class WorldGizmoDrawer
    {
        [DrawGizmo(GizmoType.NonSelected | GizmoType.InSelectionHierarchy)]
        static void DrawMarkerGizmo(WorldBuildMarker marker, GizmoType type)
        {
            var t = marker.transform;
            Gizmos.color = marker.manualLock ? new Color(1f, 0.6f, 0.1f, 0.9f)
                                             : new Color(0.2f, 0.8f, 1f, 0.5f);
            var bounds = new Bounds(t.position, Vector3.one * 2f);
            var renderers = t.GetComponentsInChildren<Renderer>();
            foreach (var r in renderers) bounds.Encapsulate(r.bounds);
            Gizmos.DrawWireCube(bounds.center, bounds.size);
            if (marker.manualLock)
                Gizmos.DrawIcon(bounds.center + Vector3.up * bounds.extents.y, "d_LockIcon", true);
        }
    }
}
