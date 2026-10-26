terraform {
  required_version = "= 1.15.8"
  required_providers {
    azapi = { source = "Azure/azapi", version = "= 2.13.0" }
  }
  backend "azurerm" {
    use_oidc             = true
    use_azuread_auth     = true
    use_cli              = false
    lookup_blob_endpoint = false
    container_name       = "tfstate"
    key                  = "router-v2.tfstate"
  }
}
provider "azapi" {
  subscription_id            = "38d8d92f-3e84-4ef5-b3da-2788a843aa70"
  tenant_id                  = "0e4545fd-804f-4acb-ad41-f955e53645c1"
  use_oidc                   = true
  skip_provider_registration = true
  enable_preflight           = false
}
locals {
  group_id = "/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourceGroups/rg-webhook-mcp-router-v2"
  app_name = "webhook-mcp-router-v2-f7076f8e38"
}
variable "sql_admin_login" { type = string }
variable "sql_admin_object_id" { type = string }
variable "runtime_ready" {
  description = "False until operator bootstraps reviewed secret references and identity grants. Does not activate app."
  type        = bool
  default     = false
}
# Native bootstrap creates only the dedicated RG and scopes CI permissions there.
# It is intentionally not managed here: no RG deletion authority is granted.
resource "azapi_resource" "foundation" {
  for_each               = jsondecode(file("${path.module}/resources.json"))
  type                   = each.value.type
  name                   = each.value.name
  parent_id              = each.value.parent_id
  location               = each.value.location
  body                   = each.value.body
  response_export_values = []
  lifecycle { prevent_destroy = true }
}
resource "azapi_resource" "storage_children" {
  for_each               = jsondecode(file("${path.module}/storage-children.json"))
  type                   = each.value.type
  name                   = each.value.name
  parent_id              = each.value.parent_id
  body                   = each.value.body
  response_export_values = []
  depends_on             = [azapi_resource.foundation]
  lifecycle { prevent_destroy = true }
}
resource "azapi_resource" "sql_server" {
  type      = "Microsoft.Sql/servers@2023-08-01"
  name      = "sql-webhook-mcp-router-v2-f7076f8e38"
  parent_id = local.group_id
  location  = "westus2"
  body = { properties = {
    version = "12.0", minimalTlsVersion = "1.2", publicNetworkAccess = "Disabled"
    administrators = {
      administratorType = "ActiveDirectory", principalType = "User"
      login             = var.sql_admin_login, sid = var.sql_admin_object_id
      tenantId          = "0e4545fd-804f-4acb-ad41-f955e53645c1", azureADOnlyAuthentication = true
    }
  } }
  response_export_values = []
  lifecycle { prevent_destroy = true }
}
resource "azapi_resource" "sql_database" {
  type       = "Microsoft.Sql/servers/databases@2023-08-01"
  name       = "router"
  parent_id  = "${local.group_id}/providers/Microsoft.Sql/servers/sql-webhook-mcp-router-v2-f7076f8e38"
  depends_on = [azapi_resource.sql_server]
  location   = "westus2"
  body = {
    sku = { name = "GP_S_Gen5_2", tier = "GeneralPurpose", family = "Gen5", capacity = 2 }
    properties = {
      autoPauseDelay                   = 60, minCapacity = 0.5, maxSizeBytes = 34359738368
      useFreeLimit                     = true, freeLimitExhaustionBehavior = "AutoPause"
      requestedBackupStorageRedundancy = "Local", zoneRedundant = false
    }
  }
  response_export_values = []
  lifecycle { prevent_destroy = true }
}
resource "azapi_resource" "app" {
  count     = var.runtime_ready ? 1 : 0
  type      = "Microsoft.Web/sites@2024-04-01"
  name      = local.app_name
  parent_id = local.group_id
  location  = "westus2"
  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [for key in ["registry_reader", "control", "delivery"] : azapi_resource.foundation[key].id]
  }
  body = {
    kind = "functionapp"
    properties = {
      serverFarmId              = azapi_resource.foundation["plan"].id
      enabled                   = false, publicNetworkAccess = "Disabled", httpsOnly = true, dailyMemoryTimeQuota = 1000
      keyVaultReferenceIdentity = azapi_resource.foundation["control"].id
      siteConfig = {
        alwaysOn                               = false, use32BitWorkerProcess = false, netFrameworkVersion = "v10.0"
        functionAppScaleLimit                  = 1, ftpsState = "Disabled", minTlsVersion = "1.2", scmMinTlsVersion = "1.2"
        remoteDebuggingEnabled                 = false
        ipSecurityRestrictionsDefaultAction    = "Deny"
        scmIpSecurityRestrictionsDefaultAction = "Deny"
        scmIpSecurityRestrictionsUseMain       = false
        ipSecurityRestrictions                 = []
        scmIpSecurityRestrictions              = []
        appSettings = [for name, value in {
          FUNCTIONS_EXTENSION_VERSION                  = "~4"
          FUNCTIONS_WORKER_RUNTIME                     = "dotnet-isolated"
          AzureWebJobsStorage__accountName             = "whmcprv2f7076f8e38"
          AzureWebJobsStorage__credential              = "managedidentity"
          WEBSITE_RUN_FROM_PACKAGE                     = "https://whmcprv2f7076f8e38.blob.core.windows.net/router-packages/${var.package_sha256}.zip"
          WEBSITE_RUN_FROM_PACKAGE_BLOB_MI_RESOURCE_ID = "SystemAssigned"
          ROUTER_AUTH_JSON                             = "@Microsoft.KeyVault(SecretUri=https://kv-whmcprv2-f7076f8e38.vault.azure.net/secrets/router-auth/)"
          ROUTER_TENANTS_JSON                          = "@Microsoft.KeyVault(SecretUri=https://kv-whmcprv2-f7076f8e38.vault.azure.net/secrets/router-tenants/)"
          RouterQueue__queueServiceUri                 = "https://whmcprv2f7076f8e38.queue.core.windows.net"
          RouterQueue__credential                      = "managedidentity"
          ROUTER_DISPATCH_ENABLED                      = "false"
          "AzureWebJobs.RouterDispatch.Disabled"       = "true"
          "AzureWebJobs.RouterReconcile.Disabled"      = "true"
          OPA_EXECUTABLE                               = "D:\\home\\site\\wwwroot\\tools\\opa.exe"
          OPA_CAPABILITIES                             = "D:\\home\\site\\wwwroot\\policies\\capabilities.json"
        } : { name = name, value = value }]
      }
    }
  }
  response_export_values = []
  depends_on             = [azapi_resource.storage_children, azapi_resource.sql_database]
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = can(regex("^[a-f0-9]{64}$", var.package_sha256))
      error_message = "Verified package digest required before app creation."
    }
  }
}

variable "package_sha256" {
  description = "Verified ZIP SHA256; object name is immutable and contains no SAS."
  type        = string
  default     = ""
  validation {
    condition     = var.package_sha256 == "" || can(regex("^[a-f0-9]{64}$", var.package_sha256))
    error_message = "Expected lowercase SHA256."
  }
}
check "runtime_package" {
  assert {
    condition     = !var.runtime_ready || can(regex("^[a-f0-9]{64}$", var.package_sha256))
    error_message = "Verified uploaded package required before app creation."
  }
}
