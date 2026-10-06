using LowPolyWorldBuilder.Data;
using UnityEngine;

namespace LowPolyWorldBuilder.Placement
{
    /// <summary>
    /// Spatial placement rules: rotation to face the street, inset from lot
    /// edges, footprint scale fitting for prefab templates.
    /// </summary>
    public static class PlacementRules
    {
        /// <summary>World rotation so a model's +Z faces the lot's street.</summary>
        public static Quaternion FacingRotation(LotFacing facing)
        {
            switch (facing)
            {
                case LotFacing.North: return Quaternion.Euler(0, 0, 0);
                case LotFacing.South: return Quaternion.Euler(0, 180, 0);
                case LotFacing.East: return Quaternion.Euler(0, 90, 0);
                default: return Quaternion.Euler(0, 270, 0);
            }
        }

        public static Vector3 LotCenter(LotData lot)
            => new Vector3(lot.rect.center.x, 0f, lot.rect.center.y);

        /// <summary>Uniform scale factor fitting a template into the lot footprint.</summary>
        public static float FitScale(Vector3 templateSize, Rect lot, bool allowVariation, float variationScale)
        {
            float fx = lot.width * 0.9f / Mathf.Max(0.01f, templateSize.x);
            float fz = lot.height * 0.9f / Mathf.Max(0.01f, templateSize.z);
            float fit = Mathf.Min(fx, fz, 1.5f);
            return allowVariation ? fit * variationScale : fit;
        }
    }
}
