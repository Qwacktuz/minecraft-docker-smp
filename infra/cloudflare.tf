resource "cloudflare_dns_record" "minecraft_v4" {
  zone_id = var.cloudflare_zone_id
  name    = var.minecraft_subdomain
  type    = "A"
  content = hcloud_server.minecraft.ipv4_address
  ttl     = 60
  proxied = false
  comment = "Managed by OpenTofu - points at MC server"
}

resource "cloudflare_dns_record" "minecraft_v6" {
  zone_id = var.cloudflare_zone_id
  name    = var.minecraft_subdomain
  content = hcloud_server.minecraft.ipv6_address
  type    = "AAAA"
  ttl     = 300
  proxied = false
}
