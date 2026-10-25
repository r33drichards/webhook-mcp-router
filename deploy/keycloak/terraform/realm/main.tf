terraform {
  required_version = "= 1.15.8"
  required_providers {
    keycloak = {
      source  = "keycloak/keycloak"
      version = "= 5.10.0"
    }
  }
  backend "azurerm" {}
}

variable "keycloak_url" {
  type = string
  validation {
    condition     = can(regex("^https://[^/?#]+$", var.keycloak_url))
    error_message = "Use the reviewed HTTPS origin, without path, query or fragment."
  }
}
variable "dip_client_secret" {
  type      = string
  sensitive = true
  ephemeral = true
}
variable "dip_secret_version" {
  type = string
}
variable "enable_dip_client" {
  type    = bool
  default = false
}

# Credentials ONLY through approved process environment; no admin secret in HCL.
# KEYCLOAK_CLIENT_SECRET for the separately bootstrapped realm administrator,
# OR KEYCLOAK_ACCESS_TOKEN containing an already authorized Keycloak token.
provider "keycloak" {
  url                      = var.keycloak_url
  realm                    = "webhook-router"
  client_id                = "terraform-webhook-router"
  keycloak_version         = "26.4.7"
  tls_insecure_skip_verify = false
}

locals {
  realm = "webhook-router"
  # First-slice explorer only; destination write is separately reviewed later.
  scopes = toset(["router:read", "requests:read", "destinations:read"])
}
resource "keycloak_openid_client_scope" "router" {
  for_each               = local.scopes
  realm_id               = local.realm
  name                   = each.value
  include_in_token_scope = true
}
resource "keycloak_openid_client" "dip" {
  realm_id                     = local.realm
  client_id                    = "dip-webhook-router"
  name                         = "dip webhook router M2M"
  enabled                      = var.enable_dip_client
  access_type                  = "CONFIDENTIAL"
  service_accounts_enabled     = true
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  full_scope_allowed           = false
  valid_redirect_uris          = []
  web_origins                  = []
  client_secret_wo             = var.dip_client_secret
  client_secret_wo_version     = var.dip_secret_version
  lifecycle { prevent_destroy = true }
}
resource "keycloak_openid_client_default_scopes" "dip" {
  realm_id       = local.realm
  client_id      = keycloak_openid_client.dip.id
  default_scopes = [for scope in keycloak_openid_client_scope.router : scope.name]
}
resource "keycloak_openid_audience_protocol_mapper" "router" {
  realm_id                 = local.realm
  client_id                = keycloak_openid_client.dip.id
  name                     = "router-audience"
  included_custom_audience = "webhook-mcp-router"
  add_to_access_token      = true
  add_to_id_token          = false
}
# No secret outputs, user accounts, admin grants, identity providers, or browser-realm resources.
