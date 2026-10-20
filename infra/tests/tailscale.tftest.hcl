# All cloud providers are mocked and this run is plan-only.
# No enrollment/destroy provisioners execute in this regression test.
mock_provider "hcloud" {
  mock_resource "hcloud_firewall" {
    defaults = { id = "123" }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = "456" }
  }
}
mock_provider "tailscale" {}
mock_provider "cloudflare" {}
mock_provider "cloudinit" {}
mock_provider "http" {}

variables {
  hcloud_token           = "test"
  ts_oauth_client_id     = "test"
  ts_oauth_client_secret = "test"
  ssh_public_key         = "test"
  cloudflare_zone_id     = "test-zone"
}

run "deferred_device_lookup_does_not_block_enrollment" {
  command = plan

  assert {
    condition     = terraform_data.minecraft_enrollment.input.hostname == "mc-prod"
    error_message = "The plan must schedule enrollment for mc-prod."
  }
}

