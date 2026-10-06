namespace LowPolyWorldBuilder.Generation
{
    /// <summary>Generic generator boundary (plan 6.1).</summary>
    public interface IWorldGenerator<TInput, TOutput>
    {
        TOutput Generate(TInput input, GenerationContext context);
    }
}
