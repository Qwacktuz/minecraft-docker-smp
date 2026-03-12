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

