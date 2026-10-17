#!/usr/bin/env python3
"""Local instance controller. Cloud and backup commands arrive in later milestones."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import tomllib
import uuid


ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9-]{0,30}")


def read_instance(name, root=None):
    root = root or ROOT
    if not NAME.fullmatch(name):
        raise ValueError("Instance names must contain lowercase letters, digits, or hyphens.")
    with (root / "instances" / f"{name}.toml").open("rb") as source:
        config = tomllib.load(source)
    if set(config) != {"role", "release", "game_port", "heap_mb", "memory_limit_mb", "players"}:
        raise ValueError(f"{name}: unexpected or missing instance settings")
    if config["role"] != "local":
        raise ValueError("This milestone supports local instances only.")
    if not isinstance(config["release"], str) or not NAME.fullmatch(config["release"]):
        raise ValueError("Invalid release name.")
    for key, low, high in (("game_port", 1024, 65535), ("heap_mb", 512, 65536),
                           ("memory_limit_mb", 1024, 131072)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f"{name}: invalid {key}")
    if config["memory_limit_mb"] < config["heap_mb"] + 512:
        raise ValueError("Container memory must leave at least 512 MB above the JVM heap.")
    if not isinstance(config["players"], list) or not all(
        isinstance(player, str) and re.fullmatch(r"[A-Za-z0-9_]{1,16}", player)
        for player in config["players"]
    ):
        raise ValueError("players must be a list of Java profile names.")
    release_path = root / "release" / f"{config['release']}.json"
    release = json.loads(release_path.read_text())
    if release.get("schema") != 1 or not re.fullmatch(
        r"itzg/minecraft-server@sha256:[0-9a-f]{64}", release.get("image", "")
    ):
        raise ValueError("Release must use schema 1 and an immutable image digest.")
    for version in (release["minecraft"]["version"], release["fabric"]["loader"],
                    release["fabric"]["installer"]):
        if not re.fullmatch(r"\d+(?:\.\d+)+", version):
            raise ValueError("Game and Fabric versions must be exact stable versions.")
    if release.get("mods") != []:
        raise ValueError("Mod artifact installation is not implemented in this milestone.")
    return config, release


def check_instances(root=None):
    root = root or ROOT
    ports = {}
    for path in sorted((root / "instances").glob("*.toml")):
        config, _ = read_instance(path.stem, root)
        port = config["game_port"]
        if port in ports:
            raise ValueError(f"Port {port} is shared by {ports[port]} and {path.stem}.")
        ports[port] = path.stem


def paths(name, root=None):
    root = root or ROOT
    state = root / ".state" / "instances" / name
    return state, root / "secrets" / "local" / f"{name}.enc.env"


def release_hash(release):
    return hashlib.sha256(json.dumps(release, sort_keys=True).encode()).hexdigest()


def compose(name, config, release, root=None):
    root = root or ROOT
    state, _ = paths(name, root)
    # Do not leak inherited CI/cloud/provider credentials into the Docker process.
    allowed = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
               "XDG_RUNTIME_DIR", "TMPDIR", "SSH_AUTH_SOCK")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({
        "SMP_IMAGE": release["image"], "SMP_MC_VERSION": release["minecraft"]["version"],
        "SMP_UID": str(os.getuid()), "SMP_GID": str(os.getgid()),
        "SMP_FABRIC_LOADER": release["fabric"]["loader"],
        "SMP_FABRIC_INSTALLER": release["fabric"]["installer"],
        "SMP_INSTANCE": name, "SMP_GAME_PORT": str(config["game_port"]),
        "SMP_HEAP": f"{config['heap_mb']}M", "SMP_MEMORY_LIMIT": f"{config['memory_limit_mb']}M",
        "SMP_PLAYERS": ",".join(config["players"]),
        "SMP_ENABLE_WHITELIST": str(bool(config["players"])).lower(),
        "SMP_DATA_DIR": str(state / "data"), "SMP_RCON_FILE": str(state / "runtime" / "rcon-password"),
    })
    command = ["docker", "compose", "--project-directory", str(root / "runtime"),
               "--env-file", os.devnull, "-f", str(root / "runtime" / "core.compose.yaml"),
               "--project-name", f"smp-{name}"]
    return command, env


def require_local_docker():
    context = os.environ.get("DOCKER_CONTEXT")
    endpoint = os.environ.get("DOCKER_HOST") if not context else None
    if endpoint is None:
        endpoint = subprocess.check_output(
            ["docker", "context", "inspect", *([context] if context else []),
             "--format", "{{.Endpoints.docker.Host}}"], text=True
        ).strip()
    if not endpoint.startswith("unix://"):
        raise ValueError("Local operations require a local Unix Docker socket, not a remote context.")


@contextmanager
def maintenance(name):
    directory = ROOT / ".state" / "locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / f"{name}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"{name}: another operation holds the instance lock") from error
        yield


def check_state(name, release):
    state, _ = paths(name)
    marker = json.loads((state / "instance.json").read_text())
    if marker.get("instance") != name or marker.get("release_sha256") != release_hash(release):
        raise ValueError("Instance identity/release changed; inspect state before proceeding.")
    if not (state / "data").is_dir():
        raise ValueError("Instance data is missing; refusing to generate a replacement world.")
    if not marker["new_world_pending"] and not (state / "data/world/level.dat").is_file():
        raise ValueError("World is missing; restore it before starting.")
    return state, marker


def initialize(name, release):
    state, secret_file = paths(name)
    if state.exists() or secret_file.exists():
        raise ValueError("Instance or credentials already exist; initialization never overwrites them.")
    password = secrets.token_urlsafe(32)
    encrypted = subprocess.run(
        ["sops", "--encrypt", "--input-type", "dotenv", "--output-type", "dotenv",
         "--filename-override", str(secret_file.relative_to(ROOT)), "/dev/stdin"],
        input=f"RCON_PASSWORD={password}\n", text=True, capture_output=True, check=True, cwd=ROOT,
    ).stdout
    if "RCON_PASSWORD=ENC[" not in encrypted:
        raise ValueError("SOPS did not produce an encrypted RCON password.")
    secret_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as target:
        target.write(encrypted)
    state.mkdir(parents=True, mode=0o700)
    (state / "data").mkdir()
    marker = {"schema": 1, "instance": name, "role": "local", "world_id": str(uuid.uuid4()),
              "release_sha256": release_hash(release), "new_world_pending": True}
    (state / "instance.json").write_text(json.dumps(marker, indent=2) + "\n")
    print(f"Initialized {name}; encrypted credentials: {secret_file.relative_to(ROOT)}")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "config", "init-local", "start", "_start",
                                            "stop", "status", "logs"])
    parser.add_argument("instance", nargs="?")
    parser.add_argument("--new-world", action="store_true", help="Explicitly initialize a blank local world")
    args = parser.parse_args()
    check_instances()
    if args.command == "validate":
        for path in sorted((ROOT / "instances").glob("*.toml")):
            config, release = read_instance(path.stem)
            command, env = compose(path.stem, config, release)
            subprocess.run(command + ["config", "--quiet"], env=env, check=True)
            print(f"Valid: {path.stem}, port {config['game_port']}, release {release['id']}")
        return
    if not args.instance:
        parser.error("this command requires an instance name")
    config, release = read_instance(args.instance)
    command, env = compose(args.instance, config, release)
    if args.command == "config":
        subprocess.run(command + ["config"], env=env, check=True)
        return
    if args.command == "start":
        _, secret_file = paths(args.instance)
        check_state(args.instance, release)
        subprocess.run(
            ["secretspec", "run", "--file", str(ROOT / "secretspec.toml"), "--profile", "local",
             "--reason", f"Start isolated local instance {args.instance}",
             "--scope", "game", "--provider", f"sops://{secret_file}?format=dotenv", "--",
             sys.executable, str(Path(__file__).resolve()), "_start", args.instance], check=True,
        )
        return
    with maintenance(args.instance):
        if args.command == "init-local":
            if not args.new_world:
                raise ValueError("Initialization requires --new-world; R2 restore arrives next milestone.")
            initialize(args.instance, release)
            return
        require_local_docker()
        if args.command == "_start":
            state, marker = check_state(args.instance, release)
            if os.getuid() == 0:
                raise ValueError("Run local instances as a normal user with Docker access.")
            password = os.environ.get("RCON_PASSWORD", "")
            if len(password) < 24 or "\n" in password:
                raise ValueError("Missing or invalid resolved RCON password.")
            runtime = state / "runtime"
            runtime.mkdir(mode=0o700, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=runtime, delete=False) as target:
                target.write(password)
                temporary = Path(target.name)
            temporary.replace(runtime / "rcon-password")
            try:
                subprocess.run(command + ["up", "-d", "--force-recreate", "--wait", "--wait-timeout", "600"],
                               env=env, check=True)
            except subprocess.CalledProcessError:
                subprocess.run(command + ["stop"], env=env, check=False)
                raise
            if not (state / "data/world/level.dat").is_file():
                subprocess.run(command + ["stop"], env=env, check=True)
                raise ValueError("Server reported healthy but world data is missing; stopped it.")
            marker["new_world_pending"] = False
            temporary = state / "instance.json.tmp"
            temporary.write_text(json.dumps(marker, indent=2) + "\n")
            temporary.replace(state / "instance.json")
        else:
            operation = {"stop": ["stop"], "status": ["ps"], "logs": ["logs", "--tail", "100"]}[args.command]
            subprocess.run(command + operation, env=env, check=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # Avoid echoing command environments or captured SOPS output containing secrets.
        message = (f"{error.cmd[0]} failed (exit {error.returncode})"
                   if isinstance(error, subprocess.CalledProcessError) else str(error))
        print(f"smp: {message}",
              file=sys.stderr)
        sys.exit(1)
