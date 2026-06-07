# Deployment secrets
# TODO: depricate enterly from tterraform 
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

# Server variables
variable "ts_tailnet" {
  description = "Tailscale tailnet name (e.g. 'user.github')"
  type        = string
  default     = "qwacktuz.github"
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
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
  description = "Instance type"
  type        = string
  default     = "cx43" # AMD64, 8 vCPU, 16GB RAM
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

