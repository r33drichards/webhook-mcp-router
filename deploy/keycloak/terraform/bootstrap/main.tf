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
    error_message = "Use the reviewed HTTPS origin only."
  }
}
variable "enable_realm" {
  type    = bool
  default = false
}
# Bootstrap ONLY: separately approved short-lived master-realm token through
# KEYCLOAK_ACCESS_TOKEN. This configuration does not create its own authority.
provider "keycloak" {
  url                      = var.keycloak_url
  realm                    = "master"
  keycloak_version         = "26.4.7"
  tls_insecure_skip_verify = false
}
resource "keycloak_realm" "router" {
  realm                  = "webhook-router"
  enabled                = var.enable_realm
  ssl_required           = "all"
  registration_allowed   = false
  reset_password_allowed = false
  lifecycle { prevent_destroy = true }
}
