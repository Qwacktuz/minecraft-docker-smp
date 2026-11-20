# Staging has no DNS: only the real VPS is mc.cactuz.dev.
resource "cloudflare_dns_record" "minecraft_v4" {
  count   = var.staging ? 0 : 1
  zone_id = var.cloudflare_zone_id
  name    = var.minecraft_subdomain
  type    = "A"
  content = hcloud_server.minecraft.ipv4_address
  ttl     = 60
  proxied = false
  comment = "Managed by OpenTofu - points at MC server"
}

resource "cloudflare_dns_record" "minecraft_v6" {
  count   = var.staging ? 0 : 1
  zone_id = var.cloudflare_zone_id
  name    = var.minecraft_subdomain
  content = hcloud_server.minecraft.ipv6_address
  type    = "AAAA"
  ttl     = 300
  proxied = false
}

# The records got a count for staging; the real VPS's keep their state.
moved {
  from = cloudflare_dns_record.minecraft_v4
  to   = cloudflare_dns_record.minecraft_v4[0]
}

moved {
  from = cloudflare_dns_record.minecraft_v6
  to   = cloudflare_dns_record.minecraft_v6[0]
}
