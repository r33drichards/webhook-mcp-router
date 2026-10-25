# Nix path for the runtime spike

Status: **definition prepared; not evaluated or built**. Nix is absent from this environment and `/nix` does not exist. No system installation was attempted.

`pins.json` records the exact Nixpkgs revision resolved through the authorized GitHub connector, the router OPA module version, the SDK research revision, and the Wasmer release/checksum reported by the runtime installer. Nixpkgs pins its default Go compiler and builder. This definition does not claim the Nixpkgs compiler matches the manually installed compiler; compare their versions during validation.

`default.nix` builds `../router` as native Go or standard WASI with `GOOS=wasip1 GOARCH=wasm`. It requires a real `vendorHash`; no fake hash or unverified hash is shipped. Capture the dependency hash from the exact final `go.mod`/`go.sum` using the pinned Nixpkgs Go workflow, then record it before claiming a reproducible build. `moduleDir` can target the Go MCP spike once its main package layout is established.

Future commands (not run):

```sh
nix-build spike/nix --argstr vendorHash '<verified SRI dependency hash>'
nix-build spike/nix --argstr vendorHash '<verified SRI dependency hash>' --arg wasm true
```

The source module and its `go.sum` must be finalized before calculating the dependency hash. Capture a second clean build's output hash before claiming reproducibility.

Use explicit source patches through `patches`. If the official MCP SDK needs a change, first prove the exact wire gap; apply a versioned patch to a pinned SDK source derivation and use a local `replace` or controlled vendoring step. A patch to the router source alone will not patch a downloaded SDK dependency. Regenerate module/vendor hashes after changes. Never patch the global Go module cache.

The runtime check remains separate: execute the resulting Wasm under the exact pinned Wasmer, supply synthetic JSON, and assert IDs. A successful Nix build would establish neither Wasmer execution nor Edge compatibility.

Primary references: [Nixpkgs Go build helpers](https://nixos.org/manual/nixpkgs/stable/#sec-language-go), [Nixpkgs source revision](https://github.com/NixOS/nixpkgs/commit/3ec636362e1816bc2f0888fa0fa2c69f1bc9e504).

## Existing WASIX Go toolchain (latest verified runtime direction)

The upstream `wasix-org/go` release **go1.25.5-6-wasix** is now pinned in `pins.json`, matching `.github/workflows/prior-art.yml`:

- Archive: `https://github.com/wasix-org/go/releases/download/go1.25.5-6-wasix/go-1.25.5-linux-x86_64.tar.gz`
- SHA-256: `c728bcffd6536f38125a652ada1da814bcf46c8cae974a873ab8f402f8d95ed0`

`wasix-go.nix` fetches that existing binary release with its verified digest; it does **not** build the compiler from source or claim a reproducible compiler bootstrap. `wasix-probe.nix` uses it for the stdlib-only networking probe with `GOTOOLCHAIN=local` so Go cannot silently download another toolchain. The older `default.nix` remains the standard-Nixpkgs-Go comparison, not the WASIX networking path.

Future command, **not run under Nix**:

```sh
nix-build spike/nix/wasix-probe.nix
```

Actual upstream-toolchain runtime evidence is separate: [CI run 40159664859](https://github.com/r33drichards/webhook-mcp-router/actions/runs/40159664859), commit `56407ccfc5454004fedc5628e0e063e008044824`, passed TCP, verified TLS, negative certificate checks, and HTTPS under Wasmer 7.5.0. The standard `http.Transport` used `net.Dialer.Control` to call `syscall.SetNonblock(fd, true)` before connect; it retained certificate verification. This is client configuration with an existing upstream toolchain, not a custom RoundTripper or a new compiler patch. See [runtime findings](../../docs/prior-art-networking.md).

These runtime passes do not validate the new Nix expressions, dependency-module builds, the entire service, or Wasmer Edge. Nix remains unavailable locally; binary packaging/loader compatibility and a clean Nix build still need validation.
