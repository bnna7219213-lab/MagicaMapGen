using System;

namespace LowPolyWorldBuilder.Placement
{
    /// <summary>
    /// Connection-port compatibility between templates (rail head to station
    /// track, dock edge to quay, runway segment to taxiway...). Rails, ports
    /// and airports in phases 5-6 validate against these rules before placing.
    /// </summary>
    public static class PortCompatibility
    {
        public static bool CanConnect(string[] portsA, string[] portsB)
        {
            if (portsA == null || portsB == null) return false;
            foreach (var a in portsA)
            foreach (var b in portsB)
                if (!string.IsNullOrEmpty(a) && string.Equals(a, b, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }
    }
}
