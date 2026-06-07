terraform {
  required_version = ">= 1.12.1"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.64"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.29"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.4"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.6"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

provider "tailscale" {
  oauth_client_id     = var.ts_oauth_client_id
  oauth_client_secret = var.ts_oauth_client_secret
  tailnet             = var.ts_tailnet
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
