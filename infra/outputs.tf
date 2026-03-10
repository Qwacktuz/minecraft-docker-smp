output "ipv4_address" {
  description = "The public IPv4 address of the server."
  value       = hcloud_server.minecraft.ipv4_address
}

output "ipv6_address" {
  description = "The public IPv6 address of the server."
  value       = hcloud_server.minecraft.ipv6_address
}
