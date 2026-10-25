using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace Router.Core;

public sealed record Route(string SubscriptionId, JsonElement Payload);

// Uses official OPA semantics. Executable/capabilities paths are operator inputs,
// never MCP arguments. No shell, inherited secrets, network builtins or URLs.
public sealed class OpaEvaluator(string executable, string capabilities)
{
    public Task<IReadOnlyList<Route>> EvaluateAsync(string source,string inputJson,IReadOnlySet<string> registeredIds,CancellationToken cancellationToken=default)
        =>EvaluateRoutesAsync(source,inputJson,registeredIds,"subscription_id",cancellationToken);
    public async Task<IReadOnlyList<DestinationRoute>> EvaluateDestinationsAsync(string source,string inputJson,IReadOnlySet<string> registeredIds,CancellationToken cancellationToken=default)
        =>(await EvaluateRoutesAsync(source,inputJson,registeredIds,"destination_id",cancellationToken)).Select(r=>new DestinationRoute(r.SubscriptionId,r.Payload)).ToArray();
    private async Task<IReadOnlyList<Route>> EvaluateRoutesAsync(string source, string inputJson,
        IReadOnlySet<string> registeredIds,string idField, CancellationToken cancellationToken)
    {
        if (!Path.IsPathFullyQualified(executable) || !Path.IsPathFullyQualified(capabilities))
            throw new InvalidOperationException("OPA_PATH_INVALID");
        if (Encoding.UTF8.GetByteCount(source) is 0 or > 32768 || Encoding.UTF8.GetByteCount(inputJson) > 65536)
            throw new InvalidOperationException("POLICY_INPUT_LIMIT");
        using var input = JsonDocument.Parse(inputJson);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(2));
        string dir = Path.Combine(Path.GetTempPath(), "router-policy-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(dir, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        try
        {
            string policy = Path.Combine(dir, "policy.rego");
            await File.WriteAllTextAsync(policy, source, deadline.Token);
            var start = new ProcessStartInfo(executable) {
                UseShellExecute = false, RedirectStandardInput = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
                CreateNoWindow = true, WorkingDirectory = dir
            };
            start.Environment.Clear();
            // Windows needs its runtime system directory; no connection strings or tokens.
            if (OperatingSystem.IsWindows() && Environment.GetEnvironmentVariable("SystemRoot") is string root)
                start.Environment["SystemRoot"] = root;
            foreach (string arg in new[] { "eval", "--stdin-input", "--format=json", "--timeout=500ms",
                "--capabilities", capabilities, "--data", policy, "data.router.routes" }) start.ArgumentList.Add(arg);
            using var process = Process.Start(start) ?? throw new InvalidOperationException("OPA_START_FAILED");
            using var kill = deadline.Token.Register(() => { try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { } });
            Task<string> stdout = ReadBounded(process.StandardOutput, 32768, deadline);
            Task<string> stderr = ReadBounded(process.StandardError, 4096, deadline);
            try
            {
                await process.StandardInput.WriteAsync(inputJson.AsMemory(), deadline.Token);
                process.StandardInput.Close();
                await process.WaitForExitAsync(deadline.Token);
                await Task.WhenAll(stdout, stderr);
                if (process.ExitCode != 0) throw new InvalidOperationException("POLICY_EVALUATION_FAILED");
                using var result = JsonDocument.Parse(await stdout);
                var rows = result.RootElement.GetProperty("result");
                if (rows.GetArrayLength() != 1) throw new InvalidOperationException("POLICY_RESULT_INVALID");
                var expressions = rows[0].GetProperty("expressions");
                if (expressions.GetArrayLength() != 1) throw new InvalidOperationException("POLICY_RESULT_INVALID");
                var values = expressions[0].GetProperty("value");
                if (values.ValueKind != JsonValueKind.Array || values.GetArrayLength() > 16)
                    throw new InvalidOperationException("POLICY_RESULT_LIMIT");
                var routes = new List<Route>();
                var seen = new HashSet<string>(StringComparer.Ordinal);
                foreach (var value in values.EnumerateArray())
                {
                    if (value.ValueKind != JsonValueKind.Object || value.EnumerateObject().Count()!=2 || value.EnumerateObject().Select(p=>p.Name).Distinct(StringComparer.Ordinal).Count()!=2 || value.EnumerateObject().Any(p => p.Name!=idField && p.Name!="payload"))
                        throw new InvalidOperationException("POLICY_RESULT_INVALID");
                    string id = value.GetProperty(idField).GetString() ?? "";
                    if (!registeredIds.Contains(id) || !seen.Add(id)) throw new InvalidOperationException("SUBSCRIPTION_NOT_ELIGIBLE");
                    var payload = value.GetProperty("payload");
                    if (Encoding.UTF8.GetByteCount(payload.GetRawText()) > 8192) throw new InvalidOperationException("PAYLOAD_LIMIT");
                    routes.Add(new Route(id, payload.Clone()));
                }
                return routes;
            }
            finally
            {
                if (!process.HasExited) { process.Kill(true); await process.WaitForExitAsync(); }
                try { await Task.WhenAll(stdout, stderr); } catch { /* bounded readers have stopped */ }
            }
        }
        finally { Directory.Delete(dir, true); }
    }

    private static async Task<string> ReadBounded(StreamReader reader, int limit, CancellationTokenSource deadline)
    {
        var text = new StringBuilder(); var buffer = new char[1024];
        while (true)
        {
            int count = await reader.ReadAsync(buffer.AsMemory(), deadline.Token);
            if (count == 0) return text.ToString();
            if (text.Length + count > limit) { deadline.Cancel(); throw new InvalidOperationException("OPA_OUTPUT_LIMIT"); }
            text.Append(buffer, 0, count);
        }
    }
}
