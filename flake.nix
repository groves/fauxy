{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    # Systems supported
    allSystems = [
      "x86_64-linux" # 64-bit Intel/AMD Linux
      "aarch64-linux" # 64-bit ARM Linux
      "x86_64-darwin" # 64-bit Intel macOS
      "aarch64-darwin" # 64-bit ARM MacOS
    ];

    # Helper to provide system-specific attributes
    nameValuePair = name: value: {inherit name value;};
    genAttrs = names: f: builtins.listToAttrs (map (n: nameValuePair n (f n)) names);
    forAllSystems = f:
      genAttrs allSystems (system:
        f {
          pkgs = import nixpkgs {inherit system;};
          inherit system;
        });
  in {
    devShells = forAllSystems ({
      pkgs,
      system,
    }: {
      default = pkgs.mkShell {
        packages = with pkgs; [
          poetry
          python310
        ];
      };
    });
  };
}
