data "cloudflare_zones" "domain" {
  name = var.cloudflare_zone_name
}

resource "cloudflare_dns_record" "minecraft_v4" {
  zone_id = data.cloudflare_zones.domain.result[0].id
  name    = var.minecraft_subdomain
  type    = "A"
  content = hcloud_server.minecraft.ipv4_address
  ttl     = 60
  proxied = false
  comment = "Managed by OpenTofu - points at MC server"
}

resource "cloudflare_dns_record" "minecraft_v6" {
  zone_id = data.cloudflare_zones.domain.result[0].id
  name    = "mc"
  content = hcloud_server.minecraft.ipv6_address
  type    = "AAAA"
  ttl     = 300
  proxied = false
}

output "proxy_ipv4" {
  description = "Public IPv4 of the Minecraft VPS"
  value       = hcloud_server.minecraft.ipv4_address
}

output "proxy_ipv6" {
  description = "Public IPv6 of the Minecraft VPS"
  value       = hcloud_server.minecraft.ipv6_address
}
