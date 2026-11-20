output "ipv4_address" {
  description = "The public IPv4 address of the server."
  value       = hcloud_server.minecraft.ipv4_address
}

output "ipv6_address" {
  description = "The public IPv6 address of the server."
  value       = hcloud_server.minecraft.ipv6_address
}

output "server_type" {
  description = "The Hetzner server type the VPS was created with (bin/server's fallback may pick another than the first)."
  value       = hcloud_server.minecraft.server_type
}

output "server_location" {
  description = "The Hetzner location the VPS was created in."
  value       = hcloud_server.minecraft.location
}
