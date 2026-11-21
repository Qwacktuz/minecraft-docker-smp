# `tofu test` (devenv `validate`): plans with mocked providers, so nothing
# real is called. The real VPS's plan must stay as it was before staging
# existed; staging must never get DNS records.
mock_provider "hcloud" {
  # Hetzner IDs are numbers.
  mock_resource "hcloud_firewall" {
    defaults = { id = "1" }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = "2" }
  }
}
mock_provider "tailscale" {}
mock_provider "cloudflare" {}

variables {
  hcloud_token           = "test"
  ts_oauth_client_id     = "test"
  ts_oauth_client_secret = "test"
  ssh_public_key         = "ssh-ed25519 AAAAprod"
  cloudflare_zone_id     = "zone"
}

run "real_vps_is_unchanged" {
  command = plan

  assert {
    condition     = length(cloudflare_dns_record.minecraft_v4) == 1 && length(cloudflare_dns_record.minecraft_v6) == 1
    error_message = "The real VPS must keep its DNS records."
  }
  assert {
    condition     = hcloud_firewall.minecraft_fw.name == "minecraft-firewall"
    error_message = "The real VPS's firewall keeps its name."
  }
  assert {
    condition     = hcloud_ssh_key.deploy_key.name == "github-actions-deploy-key" && hcloud_ssh_key.deploy_key.public_key == var.ssh_public_key
    error_message = "The real VPS keeps its SSH key."
  }
  assert {
    condition     = hcloud_server.minecraft.name == "mc-prod" && length(hcloud_server.minecraft.labels) == 0
    error_message = "The real VPS keeps its name and has no labels."
  }
}

run "staging_has_no_dns_and_is_labelled" {
  command = plan

  variables {
    staging                = true
    server_name            = "mc-staging"
    staging_ssh_public_key = "ssh-ed25519 AAAAstaging"
  }

  assert {
    condition     = length(cloudflare_dns_record.minecraft_v4) == 0 && length(cloudflare_dns_record.minecraft_v6) == 0
    error_message = "Staging must never create DNS records."
  }
  assert {
    condition     = hcloud_firewall.minecraft_fw.name == "mc-staging-firewall" && hcloud_ssh_key.deploy_key.name == "mc-staging-key"
    error_message = "Staging's firewall and key have their own names."
  }
  assert {
    condition     = hcloud_ssh_key.deploy_key.public_key == "ssh-ed25519 AAAAstaging"
    error_message = "Staging uses its own SSH key."
  }
  assert {
    condition     = hcloud_server.minecraft.labels["purpose"] == "perf-staging" && hcloud_firewall.minecraft_fw.labels["purpose"] == "perf-staging" && hcloud_ssh_key.deploy_key.labels["purpose"] == "perf-staging"
    error_message = "Every staging resource is labelled purpose=perf-staging."
  }
}

run "staging_needs_its_own_key" {
  command = plan

  variables {
    staging     = true
    server_name = "mc-staging"
  }

  expect_failures = [hcloud_ssh_key.deploy_key]
}

run "baked_image_skips_the_installs" {
  command = apply # mocked providers: nothing real is created; the cloud-init is known only then

  variables {
    server_image = "4242"
    baked        = true
  }

  assert {
    condition     = !strcontains(data.cloudinit_config.minecraft_cfg.rendered, "package_upgrade") && !strcontains(data.cloudinit_config.minecraft_cfg.rendered, "sops-v")
    error_message = "A pre-built image skips the apt upgrade, the installs and SOPS."
  }
  assert {
    condition     = strcontains(data.cloudinit_config.minecraft_cfg.rendered, "tailscale up") && strcontains(data.cloudinit_config.minecraft_cfg.rendered, "ufw --force enable") && strcontains(data.cloudinit_config.minecraft_cfg.rendered, "PasswordAuthentication no")
    error_message = "A pre-built image still joins the tailnet, hardens SSH and sets the firewall."
  }
}

run "debian_image_installs_everything" {
  command = apply # mocked providers: nothing real is created; the cloud-init is known only then

  assert {
    condition     = strcontains(data.cloudinit_config.minecraft_cfg.rendered, "package_upgrade: true") && strcontains(data.cloudinit_config.minecraft_cfg.rendered, "sops-v3")
    error_message = "Without a pre-built image, cloud-init installs everything as before."
  }
}
