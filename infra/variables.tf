# Values come from secrets/infra.enc.env as TF_VAR_* (see bin/server).
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
  default     = "qwacktuz.github"
}

variable "cloudflare_zone_id" {
  description = "cloudflare zone id"
  type        = string
  default     = null
  sensitive   = true
}

variable "cloudflare_zone_name" {
  description = "Cloudflare zone, e.g. mydomain.com"
  type        = string
  default     = "cactuz.dev"
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS Edit + R2 permissions"
  type        = string
  default     = null
  sensitive   = true
}

variable "minecraft_subdomain" {
  description = "DNS record name for the Minecraft server, e.g. mc"
  type        = string
  default     = "mc"
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
  description = "Instance type for a new VPS; bin/server passes it from SERVER_TYPES"
  type        = string
  default     = "cx33" # AMD64, 4 vCPU, 8GB RAM
}

variable "server_image" {
  description = "OS image (Hetzner's maintained debian-13; cloud-init upgrades packages)"
  type        = string
  default     = "debian-13"
}

variable "server_location" {
  description = "Datacenter location for a new VPS; bin/server passes it from SERVER_LOCATIONS"
  type        = string
  default     = "hel1"
}

