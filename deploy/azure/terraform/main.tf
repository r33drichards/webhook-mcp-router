terraform {
  required_version = "= 1.15.8"
  required_providers {
    azapi = { source = "Azure/azapi", version = "= 2.13.0" }
  }
  backend "azurerm" {
    lookup_blob_endpoint = false
    use_oidc             = true
    use_azuread_auth     = true
    use_cli              = false
  }
}
provider "azapi" {
  subscription_id            = "38d8d92f-3e84-4ef5-b3da-2788a843aa70"
  tenant_id                  = "0e4545fd-804f-4acb-ad41-f955e53645c1"
  use_oidc                   = true
  skip_provider_registration = true
  enable_preflight           = false
}
variable "existing" {
  description = "Operator-verified inventory: only existing router resources, never secrets/app settings."
  type        = map(object({ id = string, type = string, name = string, parent_id = string, location = optional(string) }))
  validation {
    condition     = length(var.existing) == 12 && alltrue([for key, r in var.existing : contains(["group", "plan", "storage", "app", "sql_server", "sql_database", "content_share", "budget", "host_blob_role", "control_identity", "delivery_identity", "registry_reader_identity"], key) && (lower(r.id) == lower("/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourceGroups/rg-webhook-mcp-router-poc") || startswith(lower(r.id), "/subscriptions/38d8d92f-3e84-4ef5-b3da-2788a843aa70/resourcegroups/rg-webhook-mcp-router-poc/providers/")) && contains(["Microsoft.Authorization/roleAssignments@2022-04-01", "Microsoft.Consumption/budgets@2024-08-01", "Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31", "Microsoft.Resources/resourceGroups@2021-04-01", "Microsoft.Sql/servers/databases@2023-08-01", "Microsoft.Sql/servers@2023-08-01", "Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01", "Microsoft.Storage/storageAccounts@2023-05-01", "Microsoft.Web/serverfarms@2024-04-01", "Microsoft.Web/sites@2024-04-01"], r.type)])
    error_message = "Exactly the 12 verified router resource keys/types are required; plan guard enforces full IDs."
  }
}
# Import-only ownership checkpoint. Freeze configuration until the real inventory
# has a reviewed no-mutation plan. This is intentionally not deployment-complete.
# GET /sites and /storageAccounts; never config/appsettings/list or listKeys.
resource "azapi_resource" "existing" {
  for_each                  = var.existing
  type                      = each.value.type
  name                      = each.value.name
  parent_id                 = each.value.parent_id
  location                  = each.value.location
  body                      = {}
  schema_validation_enabled = false
  response_export_values    = []
  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}
import {
  for_each = var.existing
  to       = azapi_resource.existing[each.key]
  id       = "${each.value.id}?api-version=${split("@", each.value.type)[1]}"
}
