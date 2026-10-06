using UnityEngine;

namespace LowPolyWorldBuilder.Config
{
    /// <summary>
    /// Cartoon color band. Materials are generated per entry and shared by
    /// submesh index across all generated meshes.
    /// </summary>
    [CreateAssetMenu(menuName = "LowPolyWorld/Style Palette", fileName = "StylePalette")]
    public sealed class StylePalette : ScriptableObject
    {
        [Header("Ground & Road")]
        public Color road = new Color(0.22f, 0.23f, 0.26f);
        public Color roadMarking = new Color(0.92f, 0.88f, 0.6f);
        public Color sidewalk = new Color(0.65f, 0.63f, 0.6f);
        public Color ground = new Color(0.45f, 0.66f, 0.35f);
        public Color water = new Color(0.25f, 0.55f, 0.75f);

        [Header("Buildings")]
        public Color[] buildingWalls =
        {
            new Color(0.94f, 0.78f, 0.55f),
            new Color(0.83f, 0.55f, 0.42f),
            new Color(0.62f, 0.74f, 0.82f),
            new Color(0.88f, 0.87f, 0.8f),
        };
        public Color[] buildingRoofs =
        {
            new Color(0.55f, 0.28f, 0.24f),
            new Color(0.3f, 0.35f, 0.45f),
            new Color(0.6f, 0.5f, 0.3f),
        };
        public Color window = new Color(0.55f, 0.78f, 0.9f);

        [Header("Building Details")]
        [Tooltip("Curtain walls, storefronts, hangar glass.")]
        public Color buildingGlass = new Color(0.5f, 0.75f, 0.88f);
        [Tooltip("Canopies, silo metal, hangar doors, signage.")]
        public Color buildingAccent = new Color(0.9f, 0.45f, 0.2f);

        [Header("Props")]
        public Color foliage = new Color(0.28f, 0.55f, 0.25f);
        public Color trunk = new Color(0.42f, 0.3f, 0.2f);
        public Color lampPost = new Color(0.2f, 0.2f, 0.22f);
    }
}
