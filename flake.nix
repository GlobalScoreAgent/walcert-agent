{
  description = "Global Score Control Center Dev Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    ethereum-nix.url = "github:nix-community/ethereum.nix";
  };

  outputs = { self, nixpkgs, flake-utils, ethereum-nix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        eth-pkgs = ethereum-nix.packages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
            python3Packages.pip
            python3Packages.virtualenv
            go-ethereum
            
            # OP Stack clients from ethereum.nix flake input
            eth-pkgs.op-geth
            eth-pkgs.op-node
            
            # Development libraries
            postgresql
            openssl
            libffi
            zlib
            gcc
            pkg-config
          ];

shellHook = ''
          echo "⚡ Entering Global Score Control Center Nix Environment ⚡"
          
          # 1. Crear el entorno virtual si no existe
          if [ ! -d .venv ]; then
            echo "Creando entorno virtual aislado (.venv)..."
            python -m venv .venv
          fi

          # 2. Activar el entorno virtual en el bash de inicialización
          source .venv/bin/activate

          # 3. Ahora sí, instalar dependencias en el entorno mutable
          echo "Installing Python dependencies from requirements.txt..."
          pip install --quiet -r requirements.txt
        '';
        };
      });
}
