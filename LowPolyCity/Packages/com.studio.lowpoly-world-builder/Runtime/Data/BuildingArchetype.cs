namespace LowPolyWorldBuilder.Data
{
    /// <summary>
    /// Architectural archetype resolved per lot. Drives massing, roof form and
    /// detail modules in BuildingMeshBuilder so that zones actually look
    /// different instead of being the same box with another color.
    /// </summary>
    public enum BuildingArchetype
    {
        House = 0,          // pitched roof, small windows, 1-3 floors
        Apartment = 1,      // flat roof, balconies, regular grid
        Office = 2,         // curtain wall, uniform bands, roof plant
        Retail = 3,         // ground-floor storefront + canopy
        Warehouse = 4,      // sawtooth or barrel roof, large cargo doors
        Hangar = 5,         // arched profile, tall clear-span doors
        Station = 6,        // long hall with elevated canopies
        ControlTower = 7,   // slender shaft + observation cab
        Silo = 8,           // cluster of cylindrical tanks
        Terminal = 9,       // wide slab with glass band + signage crown
        MetroTower = 10,    // stepped high-rise with transit bands and strong vertical fins
        MetroStation = 11,  // low concourse with twin stair mouths and canopy
        RailDepot = 12,     // multi-bay rail shed with gabled roof and clerestory
        HarborWarehouse = 13,// quay warehouse with loading canopy and container bays
        HarborSilo = 14,    // tall maritime tank cluster with pipe bridge and walkways
        Lighthouse = 15     // tapered beacon tower with lantern room
    }
}
