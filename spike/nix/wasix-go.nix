# Existing upstream binary release, not a source bootstrap. NOT NIX-TESTED.
{ pkgs }:
let
  pin = (builtins.fromJSON (builtins.readFile ./pins.json)).wasixGo;
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "upstream-wasix-go";
  version = pin.release;
  src = pkgs.fetchurl { inherit (pin) url sha256; };
  nativeBuildInputs = [ pkgs.gnutar pkgs.gzip pkgs.findutils ];
  unpackPhase = ''
    mkdir source
    tar -xzf "$src" -C source
  '';
  dontConfigure = true;
  dontBuild = true;
  installPhase = ''
    mapfile -t compilers < <(find source -type f -path '*/bin/go')
    test "''${#compilers[@]}" = 1
    root=$(dirname "$(dirname "''${compilers[0]}")")
    mkdir -p "$out"
    cp -a "$root"/. "$out"/
  '';
  meta.platforms = [ "x86_64-linux" ];
}
