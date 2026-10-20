# Enrollment happens on the VPS via cloud-init. A successful apply must also
# observe registration; creating an auth key alone is not readiness.
resource "terraform_data" "minecraft_enrollment" {
  input = {
    hostname = var.server_name
    tailnet  = var.ts_tailnet
  }
  triggers_replace = [hcloud_server.minecraft.id]

  provisioner "local-exec" {
    command = "python3 \"${path.module}/../scripts/tailscale-device.py\" wait"
    environment = {
      TS_HOST    = self.input.hostname
      TS_TAILNET = self.input.tailnet
    }
  }
}

# A list lookup tolerates an already-removed device during destroy. Apply-only
# resource preconditions below reject missing or ambiguous registrations.
data "tailscale_devices" "minecraft" {
  filter {
    name   = "hostname"
    values = [var.server_name]
  }
  depends_on = [terraform_data.minecraft_enrollment]
}

locals {
  # The provider models devices as a nested block: before a deferred read it
  # appears empty rather than unknown. The computed ID stays unknown until the
  # API read completes, so use it to defer validation until apply.
  minecraft_lookup_complete = data.tailscale_devices.minecraft.id != null
  minecraft_device          = try(one(data.tailscale_devices.minecraft.devices), null)
  # Distinct pending values keep the planned IP and node ID unknown instead of
  # fixing them to empty values before the API read has run.
  minecraft_tailscale_ipv4 = local.minecraft_lookup_complete ? [
    for address in try(local.minecraft_device.addresses, []) : address
    if try(cidrcontains("100.64.0.0/10", address), false)
  ] : [""]
}

# The provider has no managed device resource. Persist the exact node ID and
# remove it via the API before destroying/replacing the associated VPS.
# Do not use create_before_destroy: the old identity must be removed first.
resource "terraform_data" "minecraft_tailnet" {
  input = {
    device_id = local.minecraft_lookup_complete ? try(local.minecraft_device.node_id, null) : ""
    hostname  = var.server_name
    server_id = hcloud_server.minecraft.id
  }
  # Lookup values can be unknown while a bootstrap key rotates. Only VPS
  # replacement should destroy this resource and revoke its device identity.
  triggers_replace = [hcloud_server.minecraft.id]

  provisioner "local-exec" {
    when    = destroy
    command = "python3 \"${path.module}/../scripts/tailscale-device.py\" delete"
    environment = {
      TS_DEVICE_ID = self.input.device_id
    }
  }

  lifecycle {
    precondition {
      condition     = local.minecraft_lookup_complete
      error_message = "The Tailscale device lookup did not complete."
    }
    precondition {
      condition     = local.minecraft_lookup_complete ? length(data.tailscale_devices.minecraft.devices) == 1 : true
      error_message = "Expected exactly one Minecraft Tailscale device. For a missing existing VPS, host re-enrollment is required; for duplicates, resolve the hostname conflict."
    }
    precondition {
      condition     = local.minecraft_lookup_complete ? try(local.minecraft_device.authorized && contains(local.minecraft_device.tags, "tag:server"), false) : true
      error_message = "The Minecraft device must be authorized and tagged tag:server."
    }
    precondition {
      condition     = local.minecraft_lookup_complete ? length(local.minecraft_tailscale_ipv4) == 1 : true
      error_message = "The Minecraft device must have exactly one Tailscale IPv4 address."
    }
  }
}
