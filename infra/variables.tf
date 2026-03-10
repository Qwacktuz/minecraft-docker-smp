# Deployment
variable "hcloud_token" {
  description = "Hetzner Cloud API Token"
  type        = string
  sensitive   = true
}

variable "ts_oauth_client_id" {
  description = "Tailscale OAuth Client ID"
  type        = string
  sensitive   = true
}

variable "ts_oauth_client_secret" {
  description = "Tailscale OAuth Client Secret"
  type        = string
  sensitive   = true
}

variable "ts_tailnet" {
  description = "Tailscale tailnet name (e.g. 'user.github')"
  type        = string
}

variable "github_repo_url" {
  description = "HTTPS URL of git repo"
  type        = string
  default     = "https://github.com/qwacktuz/infra-minecraft"
}

variable "ssh_public_key" {
  description = "Public SSH key for the deployer user"
  type        = string
}

variable "username" {
  description = "The non-root user to create (must match GitHub vars.USERNAME)"
  type        = string
  default     = "deployer"
}

variable "server_name" {
  description = "Hostname of the server"
  type        = string
  default     = "mc-prod"
}

variable "server_type" {
  description = "Instance type"
  type        = string
  default     = "cx33" # AMD64, 4 vCPU, 8GB RAM
}

variable "server_image" {
  description = "Instance type"
  type        = string
  default     = "debian-13"
}

variable "server_location" {
  description = "Datacenter location"
  type        = string
  default     = "hel1"
}

# Server secrets
variable "rcon_password" { sensitive = true }
variable "grafana_password" { sensitive = true }
variable "mc_ops" { default = "" }
variable "mc_whitelist" { default = "" }
variable "r2_bucket_name" { sensitive = true }
variable "r2_access_key_id" { sensitive = true }
variable "r2_secret_access_key" { sensitive = true }
variable "r2_endpoint" { sensitive = true }
variable "restic_password" { sensitive = true }

# Tofu is able to upload secrets
variable "ssh_private_key_path" {
  description = "Private deploy key"
  type        = string
  default     = "~/.ssh/mc-prod_id_ed25519"
}

variable "allowed_ssh_ips" {
  description = "Additional CIDRs allowed to SSH"
  type        = list(string)
  default     = []
}
