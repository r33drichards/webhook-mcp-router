# Nix runtime evidence

Date: 2026-10-25. Scope: prerequisites and prepared reproducible build path only.

## Executed checks

Exact argv, stdout, stderr, and exit status are in `spike/nix/logs/prerequisites.json`.

| Command | Exit | Observation |
| --- | --- | --- |
| `command -v nix` | 1 | No executable on PATH |
| `command -v nix-instantiate` | 1 | No executable on PATH |
| `test -d /nix` | 1 | No Nix store directory |
| `/usr/bin/go version` | 1 | `Go: Unknown option: version` |
| `/usr/bin/go --help` | 0 | This executable is a local Go board game, not the compiler |
| `python -m json.tool spike/nix/pins.json` | 0 | Manifest is valid JSON |

The parent/runtime agent is installing a real official Go toolchain separately; the `/usr/bin/go` observation must not be confused with that installation.

## Source pin and prepared build

The authorized GitHub connector fetched `https://api.github.com/repos/NixOS/nixpkgs/commits/nixos-unstable` and returned commit `3ec636362e1816bc2f0888fa0fa2c69f1bc9e504`.

Prepared `spike/nix/default.nix`, `pins.json`, and README. The definition selects pinned Nixpkgs, accepts a Go module source, and supports native versus WASI compilation. It deliberately requires a verified module `vendorHash`. No dependency hash was invented. SDK patching is conditional and documented separately from root module patches.

No Nix evaluation, Go compilation through Nix, Wasmer execution through Nix, or reproducibility comparison ran. JSON validation is not Nix syntax validation.

## Blockers and limitations

Nix is unavailable, and its conventional `/nix` store is absent. A system-wide installation was not attempted; no permission denial or approval request occurred. This blocks Nix evaluation/build in the current environment. Smallest next step: an environment with a working Nix installation/store, then finalize the Go module sources, obtain the real dependency hash, and execute native/WASI builds plus assertions.

One direct Python urllib request for Nixpkgs commit metadata failed with `Tunnel connection failed: 403 Forbidden`. It was not retried or tunneled around. The existing authorized GitHub connector supplied public source metadata; no binary was downloaded through it. This request had no mutation or uncertain side effects.

Primary sources: [Nixpkgs manual](https://nixos.org/manual/nixpkgs/stable/#sec-language-go), [pinned revision](https://github.com/NixOS/nixpkgs/commit/3ec636362e1816bc2f0888fa0fa2c69f1bc9e504).
