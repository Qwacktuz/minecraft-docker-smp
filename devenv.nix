# Development environment for this project: https://devenv.sh
#
#   devenv shell        enter it (or let direnv load it via .envrc)
#   server start vps    the project's start/stop entry point (bin/server)
#   validate            everything CI checks, run locally
#   devenv test         same as `validate`, in a fresh environment
#
# Not provided here: the Docker daemon (run OrbStack or Docker Desktop) and the
# Tailscale client (macOS app), which both need system-level installs.
{ pkgs, ... }:

{
  packages = with pkgs; [
    # Running the server
    docker # CLI with the Compose and buildx plugins; talks to OrbStack's socket
    git # (ssh comes from macOS; Nix's build rejects UseKeychain in ~/.ssh/config)

    # Secrets
    sops
    age
    secretspec # used by the bin/smp local-core experiment

    # Checks (mirrors .github/workflows/validate.yml)
    shellcheck
    actionlint
    jq
  ];

  languages.python.enable = true; # scripts/smp.py and tests need Python 3.11+
  languages.opentofu.enable = true;

  # Secrets are never loaded into the shell: they stay SOPS-encrypted in secrets/
  # and are decrypted per command (bin/server, scripts/deploy.sh).
  dotenv.disableHint = true;

  enterShell = ''
    export SOPS_AGE_KEY_FILE="''${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
  '';

  scripts.server = {
    description = "Start/stop the world locally or on the VPS (bin/server)";
    exec = ''exec "$DEVENV_ROOT/bin/server" "$@"'';
  };

  scripts.validate = {
    description = "Run every check (CI runs exactly this via `devenv test`)";
    exec = ''
      set -euo pipefail
      cd "$DEVENV_ROOT"
      for script in scripts/*.sh bin/server; do bash -n "$script"; done
      shellcheck scripts/deploy.sh bin/smp bin/server
      actionlint
      python3 -m unittest discover -s tests
      bin/smp validate
      tofu -chdir=infra fmt -check
      tofu -chdir=infra init -backend=false -lockfile=readonly >/dev/null
      tofu -chdir=infra validate

      # Monitoring configs are checked with the same images Compose runs.
      if docker info >/dev/null 2>&1; then
        docker run --rm -v "$PWD/alloy/config.alloy:/etc/alloy/config.alloy:ro" \
          grafana/alloy:latest validate /etc/alloy/config.alloy
        docker run --rm -v "$PWD/loki/loki-config.yaml:/etc/loki/local-config.yaml:ro" \
          grafana/loki:latest -config.file=/etc/loki/local-config.yaml -verify-config=true
      elif [ -n "''${CI:-}" ]; then
        echo "validate: CI needs a Docker daemon for the Alloy/Loki checks" >&2
        exit 1
      else
        echo "validate: Docker isn't running; skipped the Alloy/Loki checks (start OrbStack)"
      fi
    '';
  };

  git-hooks.hooks = {
    shellcheck = {
      enable = true;
      # Same files as CI; the older scripts/*.sh and archive/ aren't lint-clean yet.
      files = "^(scripts/deploy\\.sh|bin/(smp|server))$";
    };
    actionlint.enable = true;
    nixfmt.enable = true;
    tofu-fmt = {
      enable = true;
      name = "tofu fmt";
      entry = "${pkgs.opentofu}/bin/tofu fmt -check";
      files = "\\.tf$";
    };
  };

  enterTest = "validate";
}
