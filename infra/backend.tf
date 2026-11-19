terraform {
  backend "s3" {
    # Provided by bin/server from secrets/infra.enc.env via -backend-config
    bucket   = ""
    key      = "prod/terraform.tfstate"
    region   = "auto"
    endpoint = ""

    # Needed for R2 compatible S3 storage
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true
    # R2 checksums are incompatible with the AWS SDK's defaults.
    skip_s3_checksum = true

    # Lock the state while tofu runs (a .tflock object next to it), so two
    # runs can never apply at once.
    use_lockfile = true
  }
}
