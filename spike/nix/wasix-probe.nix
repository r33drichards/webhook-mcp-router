# Pinned stdlib-only probe build using the existing upstream toolchain.
# Definition prepared only; Nix is absent locally.
{ system ? builtins.currentSystem }:
let
  pin = (builtins.fromJSON (builtins.readFile ./pins.json)).nixpkgs;
  pkgs = import (builtins.fetchGit {
    inherit (pin) url rev;
    shallow = true;
  }) { inherit system; };
  go = import ./wasix-go.nix { inherit pkgs; };
in
pkgs.runCommand "wasix-go-network-probe" { nativeBuildInputs = [ go ]; } ''
  export GOTOOLCHAIN=local GOOS=wasip1 GOARCH=wasm CGO_ENABLED=0 GO111MODULE=off
  export GOCACHE="$TMPDIR/go-cache"
  mkdir -p "$out"
  go version > "$out/toolchain-version.txt"
  go build -trimpath -buildvcs=false -o "$out/probe.wasm" ${../prior-art/main.go}
''
