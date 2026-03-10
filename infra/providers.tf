terraform {
  required_version = ">= 1.11.5"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.60"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.28"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.3"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.5"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

provider "tailscale" {
  oauth_client_id     = var.tailscale_oauth_client_id
  oauth_client_secret = var.tailscale_oauth_client_secret
  tailnet             = var.tailscale_tailnet
}
