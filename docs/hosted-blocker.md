> Superseded in part by [the broader prior-art review](prior-art-networking.md): an existing WASIX Go fork has now passed real TCP and certificate-verified TLS tests under Wasmer. Standard HTTP still times out; do not treat the earlier search as proof that no existing solution exists.

# Hosted E2E blocker after green CI

The selected unmodified Go 1.27.3 `GOOS=wasip1 GOARCH=wasm` build can execute SDK CGI and embedded OPA, but its default outbound `net/http.Transport` cannot establish a real callback connection. [Official Go source](https://github.com/golang/go/blob/go1.27.3/src/net/net_fake.go) selects fake networking for `wasip1`; `fakeConnect` connects within the guest's socket map. The installed `net/fd_fake.go` separately allows operations on inherited accepted sockets; that does not provide arbitrary outbound dialing. Previous actual Wasmer outbound HTTP/TCP probes failed while native controls passed.

[WCGI](https://docs.wasmer.io/edge/learn/deployment-modes/) maps incoming HTTP to environment/stdin and response stdout in a fresh instance. It does not automatically replace Go's outbound transport. Therefore the current `spike/hosted` binary cannot deliver the requested real callback or perform the exact events/subscribe verification challenge. More event-method scaffolding or a deployment manifest cannot fix that transport boundary. This is specific to the selected Go target/transport, not a claim that Wasmer or Edge generally lacks networking.

Required change: a verified Go-compatible Wasmer host networking/HTTP adapter, with actual host-side outbound receipt evidence, wired into the service's HTTP client. No such compatible adapter has been verified for the tested toolchain. A WASIX-capable different runtime or an external delivery worker would change the selected architecture and must be described as such; a CI relay must not be represented as delivery by the Go guest. Nix release work is independent and is not the essential blocker for this minimal test.

## Storage and cost

The parent verified the account's Free plan and stored the approved dedicated WASMER_TOKEN Actions secret. This agent did not retrieve or recreate it. [Published Hobby pricing](https://wasmer.io/pricing) includes 1 GB volume storage, 1 GB package storage, six CPU hours and one million requests. A tiny authenticated synthetic fixture is plausibly within those quotas, subject to remaining account allowance. No paid upgrade or billing change is authorized or attempted.

[Volumes](https://docs.wasmer.io/edge/learn/volumes/) are declared with a name/mount and persist across invocations, but currently have RWX semantics across nodes. A per-ID marker fixture avoids pretending shared SQLite is safe; atomic creation and visibility still require hosted validation. The registration and receipt directories must remain separate. No volume or database has been provisioned.

## Concrete status

- Public code commit `23fa45d9a39a3e840066355420a86a8a42a787e3` passed both jobs in [CI run 40158341557](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40158341557).
- SDK initialize/tools/create/fresh-instance mapped-file readback and embedded Go OPA evaluation passed in actual Wasmer guests on GitHub runners.
- Hosted deployment, live HTTP initialize, Edge readback, real subscription verification and callback receipt: **not attempted / not proven**.
- Deployment gate stays closed on the actual outbound transport/hosted-readiness gap. This is not an automatic approval denial and there is no uncertain remote deployment.
- The connector exposes no workflow-dispatch action. Once a reviewed deployment is actually ready, the parent-owned browser can trigger the authorized manual workflow; no concurrent browser use or alternate API route was attempted here.
