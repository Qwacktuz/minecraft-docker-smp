resource "hcloud_ssh_key" "deploy_key" {
  name       = "github-actions-deploy-key"
  public_key = var.ssh_public_key
}

# Fetch the current runner's IP for dynamic provisioning
# In case I change product etc.
# FIXME: should be changed if using CI/CD pipeline
# But works for now since I am pushing updates from my local machine
data "http" "runner_ip" {
  url = "https://ipv4.icanhazip.com"
}

# Generate a one-time ephemeral Tailscale Auth key using OAuth credentials
resource "tailscale_tailnet_key" "server_key" {
  reusable      = false
  ephemeral     = true
  preauthorized = true
  expiry        = 3600           # 1 hour for bootstrap
  tags          = ["tag:server"] # scuffed ACL fix later
}

# Prepare the cloud-init config using the cloudinit provider
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

# First layer of defense
resource "hcloud_firewall" "minecraft_fw" {
  name = "minecraft-firewall"

  # Minecraft TCP/UDP
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "25565"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "25565"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Simple Voice Chat UDP
  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "24454"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Enable SSH: Restricted to runner 
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["${chomp(data.http.runner_ip.response_body)}/32"]
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
    prevent_destroy = true # Set to true when statble to prevent deleting state
    ignore_changes  = [user_data]
  }
}
