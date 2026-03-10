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
resource "ts_tailnet_key" "server_key" {
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
      ts_authkey  = ts_tailnet_key.server_key.key
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

  # Enable SSH: Restricted to runner + allowed IPs
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = distinct(concat(["${chomp(data.http.runner_ip.response_body)}/32"], var.allowed_ssh_ips))
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
  }
}

resource "terraform_data" "env_secrets" {
  # Tell Tofu to re-run this block if any secret changes
  triggers_replace = [
    var.rcon_password, var.grafana_password, var.mc_ops, var.mc_whitelist,
    var.r2_bucket_name, var.r2_access_key_id, var.r2_secret_access_key,
    var.r2_endpoint, var.restic_password
  ]

  # Wait for the server to be fully created and cloud-init to finish
  depends_on = [hcloud_server.minecraft]

  connection {
    type        = "ssh"
    user        = var.username
    host        = hcloud_server.minecraft.ipv4_address
    private_key = file(pathexpand(var.ssh_private_key_path))
  }

  # Ensure the app directory exists
  provisioner "remote-exec" {
    inline = [
      # Ensure cloud init is done
      "until [ -f /var/lib/cloud/instance/boot-finished ]; do echo 'Waiting for cloud-init...'; sleep 2; done",
      # Create app dir for server
      "mkdir -p /home/${var.username}/app"
    ]
  }

  # Securely upload the secrets file
  provisioner "file" {
    content     = <<-EOF
      RCON_PASSWORD=${var.rcon_password}
      GRAFANA_PASSWORD=${var.grafana_password}
      MC_OPS=${var.mc_ops}
      MC_WHITELIST=${var.mc_whitelist}
      R2_BUCKET_NAME=${var.r2_bucket_name}
      R2_ACCESS_KEY_ID=${var.r2_access_key_id}
      R2_SECRET_ACCESS_KEY=${var.r2_secret_access_key}
      R2_ENDPOINT=${var.r2_endpoint}
      RESTIC_PASSWORD=${var.restic_password}
    EOF
    destination = "/home/${var.username}/app/.env.secrets"
  }
}
