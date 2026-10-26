using Microsoft.Data.SqlClient;
namespace Router.Migrator;
// Connection-only warmup. Never receives a migration/script/transaction callback.
public static class ConnectionWarmup {
 public static bool IsResumeOnly(IEnumerable<int> numbers) {
  var errors=numbers.ToArray();return errors.Length>0 && errors.All(n=>n==40613);
 }
 public static Task OpenAsync(Func<SqlConnection> create,CancellationToken cancellation=default)=>RetryAsync(async ct=> {
  using var connection=create();await connection.OpenAsync(ct);
 },e=>e is SqlException sql && IsResumeOnly(sql.Errors.Cast<SqlError>().Select(x=>x.Number)),cancellation);
 // Injectable delay/error classifier for deterministic offline tests; production
 // OpenAsync fixes the classifier to SQL 40613 and performs only OpenAsync.
 public static async Task RetryAsync(Func<CancellationToken,Task> open,Func<Exception,bool> resumable,CancellationToken cancellation=default,Func<TimeSpan,CancellationToken,Task>? delay=null) {
  using var budget=CancellationTokenSource.CreateLinkedTokenSource(cancellation);
  budget.CancelAfter(TimeSpan.FromMinutes(2));
  for(int attempt=1;;attempt++) {
   budget.Token.ThrowIfCancellationRequested();
   try {await open(budget.Token);return;}
   catch(Exception error) when(attempt<6 && !budget.IsCancellationRequested && resumable(error)) {
    Console.Error.WriteLine($"SQL_CONNECTION_WARMUP code=40613 attempt={attempt} retry=true");
    await (delay??Task.Delay)(TimeSpan.FromSeconds(10),budget.Token);
   }
  }
 }
}
