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
