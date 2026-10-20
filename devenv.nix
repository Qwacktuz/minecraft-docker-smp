{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  # Secrets are automatically populated from secretspec.toml
  env.AWS_SECRET_ACCESS_KEY = config.secretspec.secrets.AWS_SECRET_ACCESS_KEY;
  env.AWS_ACCESS_KEY_ID = config.secretspec.secrets.AWS_ACCESS_KEY_ID;
  env.HCLOUD_TOKEN = config.secretspec.secrets.HCLOUD_TOKEN;
  env.TAILSCALE_API_KEY = config.secretspec.secrets.TAILSCALE_API_KEY;
  env.TAILSCALE_TAILNET = config.secretspec.secrets.TAILSCALE_TAILNET;

  # https://devenv.sh/basics/
  # env.GREET = "devenv";

  # https://devenv.sh/packages/
  packages = with pkgs; [
    git
    jj
    # secretspec
  ];

  # https://devenv.sh/languages/
  languages.opentofu.enable = true;
  languages.shell.enable = true;

  # https://devenv.sh/processes/
  # processes.dev.exec = "${lib.getExe pkgs.watchexec} -n -- ls -la";

  # https://devenv.sh/services/
  # services.postgres.enable = true;

  # https://devenv.sh/scripts/
  # scripts.hello.exec = ''
  #   echo hello from $GREET
  # '';

  # https://devenv.sh/basics/
  # enterShell = ''
  #   hello         # Run scripts directly
  #   git --version # Use packages
  # '';

  # https://devenv.sh/tasks/
  # tasks = {
  #   "myproj:setup".exec = "mytool build";
  #   "devenv:enterShell".after = [ "myproj:setup" ];
  # };

  # https://devenv.sh/tests/
  # enterTest = ''
  #   echo "Running tests"
  #   git --version | grep --color=auto "${pkgs.git.version}"
  # '';

  # https://devenv.sh/git-hooks/
  git-hooks.hooks.shellcheck.enable = true;

  # See full reference at https://devenv.sh/reference/options/
}
