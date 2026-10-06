using System.Collections.Generic;
using LowPolyWorldBuilder.Data;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace LowPolyWorldBuilder.Editor.Scene
{
    /// <summary>
    /// Owns the generated root node. Cleanup only removes objects that carry
    /// a WorldBuildMarker with matching profile/region and no manualLock —
    /// never deletes arbitrary user scene content (plan 5.3).
    /// </summary>
    public static class GeneratedRootManager
    {
        public const string RootPrefix = "LPW_";

        public static GameObject FindOrCreateRoot(string profileGuid, int seed, string regionKey, bool create, out bool existed)
        {
            foreach (var go in Object.FindObjectsByType<WorldBuildMarker>(FindObjectsSortMode.None))
            {
                if (go.profileGuid == profileGuid && go.regionKey == regionKey)
                {
                    existed = true;
                    return go.gameObject;
                }
            }
            existed = false;
            if (!create) return null;

            var root = new GameObject(RootPrefix + regionKey);
            var marker = root.AddComponent<WorldBuildMarker>();
            marker.profileGuid = profileGuid;
            marker.seed = seed;
            marker.regionKey = regionKey;
            Undo.RegisterCreatedObjectUndo(root, "Create LPW Root");
            return root;
        }

        /// <summary>Remove generated children, honoring manualLock at any depth.
        /// Fix C4: recurse into a container that holds a locked descendant so its
        /// UNLOCKED siblings are still cleared. The earlier one-level check either
        /// destroyed a locked grandchild with its unlocked parent (original bug)
        /// or preserved the whole container, leaving every stale block behind on
        /// the next rebuild (duplication regression). Verified by audit_sim/sim_c4.js.</summary>
        public static int ClearGeneratedChildren(GameObject root)
        {
            if (root == null) return 0;
            return ClearRecursive(root.transform);
        }

        static int ClearRecursive(Transform parent)
        {
            int removed = 0;
            for (int i = parent.childCount - 1; i >= 0; i--)
            {
                var child = parent.GetChild(i).gameObject;
                var marker = child.GetComponent<WorldBuildMarker>();
                if (marker != null && marker.manualLock)
                    continue;                       // locked node: preserve entire subtree
                if (HasLockDeep(child))
                {
                    removed += ClearRecursive(child.transform); // keep the lock-ancestor chain
                    continue;
                }
                Undo.DestroyObjectImmediate(child);
                removed++;
            }
            return removed;
        }

        /// <summary>Check if a GameObject or any of its descendants has manualLock=true.
        /// Returns true if the sub-tree should be preserved (some node is locked).</summary>
        static bool HasLockDeep(GameObject go)
        {
            var marker = go.GetComponent<WorldBuildMarker>();
            if (marker != null && marker.manualLock) return true;
            // Recurse into children — if any descendant is locked, preserve go too.
            foreach (Transform t in go.transform)
                if (HasLockDeep(t.gameObject)) return true;
            return false;
        }

        /// <summary>Destroy all generated roots for a profile (used by 'Clean' action).
        /// Fix C4: skip any marker whose subtree still contains a lock (destroying an
        /// ancestor would take the locked descendant with it), and guard against
        /// markers already destroyed as part of an ancestor's subtree this pass —
        /// touching a destroyed MonoBehaviour throws MissingReferenceException.</summary>
        public static int CleanAll(string profileGuid)
        {
            int removed = 0;
            var markers = Object.FindObjectsByType<WorldBuildMarker>(FindObjectsSortMode.None);
            foreach (var m in markers)
            {
                if (m == null) continue;                       // already destroyed via an ancestor
                if (m.profileGuid != profileGuid) continue;
                if (HasLockDeep(m.gameObject)) continue;       // preserve locked subtree
                Undo.DestroyObjectImmediate(m.gameObject);
                removed++;
            }
            return removed;
        }
    }
}
