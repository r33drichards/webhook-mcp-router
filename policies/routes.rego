package router
import rego.v1

# input contains authenticated source metadata and eligible subscriptions only.
subscription_ids := sort([s.id |
    some s in input.subscriptions
    input.event.provider == "github"
    input.event.type == "pull_request"
    input.event.body.action == "opened"
    input.event.body.repository.full_name == s.repository
])
