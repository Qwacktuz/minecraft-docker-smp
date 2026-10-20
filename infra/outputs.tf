output "ipv4_address" {
  description = "The public IPv4 address of the server."
  value       = hcloud_server.minecraft.ipv4_address
}

output "ipv6_address" {
  description = "The public IPv6 address of the server."
  value       = hcloud_server.minecraft.ipv6_address
}

output "tailscale_ipv4" {
  description = "Registered Minecraft device address, without relying on runner DNS."
  value       = try(one(local.minecraft_tailscale_ipv4), null)
  depends_on  = [terraform_data.minecraft_tailnet]
}
