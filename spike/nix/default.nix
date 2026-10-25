# Unexecuted build definition. vendorHash is deliberately required, never faked.
# Example after calculating the hash from the exact module source:
# nix-build spike/nix --argstr vendorHash 'sha256-...' --arg wasm true
{ system ? builtins.currentSystem
, vendorHash
, wasm ? false
, moduleDir ? ../router
, patches ? []
}:
let
  pins = builtins.fromJSON (builtins.readFile ./pins.json);
  nixpkgs = builtins.fetchGit {
    inherit (pins.nixpkgs) url rev;
    shallow = true;
  };
  pkgs = import nixpkgs { inherit system; };
in
pkgs.buildGoModule {
  pname = if wasm then "webhook-router-wasi-spike" else "webhook-router-native-spike";
  version = "0.0.0-spike";
  src = pkgs.lib.cleanSource moduleDir;
  inherit vendorHash patches;
  # SDK-specific patches must target vendored SDK source, not only this module.
  # Supply a source/module replacement and regenerate go.sum/vendorHash as needed.
  env.CGO_ENABLED = "0";
  env.GOTOOLCHAIN = "local";
  doCheck = false; # Runtime assertions are separate; never run a Wasm file natively.
  buildPhase = ''
    runHook preBuild
    ${pkgs.lib.optionalString wasm ''export GOOS=wasip1 GOARCH=wasm''}
    go build -mod=vendor -trimpath -buildvcs=false -o spike${pkgs.lib.optionalString wasm ".wasm"} .
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin"
    cp spike${pkgs.lib.optionalString wasm ".wasm"} "$out/bin/"
    runHook postInstall
  '';
}
