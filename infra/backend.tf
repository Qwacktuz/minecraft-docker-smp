terraform {
  backend "s3" {
    # Will be provided at runtime via the -backend-config flag
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
  }
}
