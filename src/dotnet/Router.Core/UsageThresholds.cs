namespace Router.Core;

// Calendar-month-to-date subscription aggregate, not a rolling alert window.
public static class UsageThresholds
{
    public const decimal ExecutionGrant = 1_000_000m;
    public const decimal GbSecondsGrant = 400_000m;
    public const decimal UnitsPerGbSecond = 1_024_000m;
    public static IReadOnlyList<int> Crossed(decimal executions, decimal units)
    {
        if (executions < 0 || units < 0) throw new ArgumentOutOfRangeException(nameof(executions));
        return new[] { 80, 90, 100 }.Where(percent =>
            executions >= ExecutionGrant * percent / 100m ||
            units >= GbSecondsGrant * UnitsPerGbSecond * percent / 100m).ToArray();
    }
}
