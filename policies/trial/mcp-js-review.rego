package router
import rego.v1

# Generic routing contract. No URL or credential in a policy.
# Destination remains unregistered until the owner chooses its actual URL.
routes := [{"destination_id": d.id, "payload": input.payload} |
    d := input.destinations[_]
    d.tags[_] == "review"
    input.context.provider == "github"
    input.original.repository.id == 961207108
    input.original.repository.full_name == "r33drichards/mcp-js"
    input.context.event_type == "pull_request"
    input.original.action == "labeled"
    input.original.label.name == "review"
]
