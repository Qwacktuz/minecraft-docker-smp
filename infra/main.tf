resource "hcloud_ssh_key" "deploy_key" {
  name       = "github-actions-deploy-key"
  public_key = var.ssh_public_key
}

# Single-use bootstrap key. Ephemeral: the device disappears once a deleted VPS
# goes offline, so the next VPS gets the same Tailscale name.
resource "tailscale_tailnet_key" "server_key" {
  reusable      = false
  ephemeral     = true
  preauthorized = true
  expiry        = 3600 # 1 hour for bootstrap
  tags          = ["tag:server"]
}

data "cloudinit_config" "minecraft_cfg" {
  gzip          = false
  base64_encode = false

  part {
    content_type = "text/cloud-config"
    content = templatefile("${path.module}/cloud-init.yaml", {
      ts_authkey  = tailscale_tailnet_key.server_key.key
      hostname    = var.server_name
      username    = var.username
      ssh_pub_key = var.ssh_public_key
    })
  }
}

# Only the game is public. SSH is reachable over Tailscale only.
resource "hcloud_firewall" "minecraft_fw" {
  name = "minecraft-firewall"

  rule {
    description = "Minecraft"
    direction   = "in"
    protocol    = "tcp"
    port        = "25565"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "Simple Voice Chat mod"
    direction   = "in"
    protocol    = "udp"
    port        = "24454"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "Webcam mod"
    direction   = "in"
    protocol    = "udp"
    port        = "25454"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "minecraft" {
  name         = var.server_name
  image        = var.server_image
  server_type  = var.server_type
  location     = var.server_location
  firewall_ids = [hcloud_firewall.minecraft_fw.id]
  ssh_keys     = [hcloud_ssh_key.deploy_key.id]

  user_data = data.cloudinit_config.minecraft_cfg.rendered

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  lifecycle {
    # bin/server stop deletes the server on purpose, after a verified backup.
    prevent_destroy = false
    # Cloud-init changes apply to the next VPS, never by replacing a running one.
    ignore_changes = [user_data]
  }
}
