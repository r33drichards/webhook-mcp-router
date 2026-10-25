# Superseding checkpoint

The clarified publication authorization was accepted on the single allowed retry: main advanced to ca5d3bf. The historical rejection below is resolved. Current published code is 0430df942417eb3c43cb5a562aafb7cc93c080c3. Actual SDK/OPA native tests and WASIX Wasm compilation passed; guest UDP DNS was denied by Wasmer inbound auto-bind policy. Standard TCP resolver tests now use exact outbound loopback destinations, and independent IP/TLS/events stages run even if DNS fails. No deployment has occurred.

# Actual service compile checkpoint

Prepared actual official Go SDK + native OPA integration, events extension lifecycle, signed challenge, policy management/ingress, configured nonblocking HTTP transport, and DNS/TLS/concurrency/cancellation tests. Pinned existing WASIX Go 1.25.5 release; GOTOOLCHAIN=local prevents compiler fallback. Nix expressions remain untested locally.

Local native tests did not reach compilation: OPA dependency/checksum entries are unavailable in the permitted local module supply. No previously denied dependency download was retried. The authorized GitHub CI path uses normal module resolution and must still establish actual service compilation and execution.

Remote commit object ca5d3bfec4bb980e140ef9a024716662a373ed7c was created. Updating public main from 35a181bfd93aaea6a139e869d6d5d0e8f4e2880b to that commit was explicitly rejected by automatic approval review. Stated reason: it retained the initial no-push restriction and considered later authorization unavailable. No alternate push route or retry was attempted. No new service CI run or hosted deployment resulted.

The main.go discovery resultType preservation follow-up is on disk; it may need a new tree/commit before a newly authorized branch update. Preserve the rejected commit object as historical, not a tested branch state.

Further hosted gates remain real: actual SDK/OPA guest tests, exact fresh-instance events/challenge/callback checks, shared registration database/transport and Edge persistence semantics, and protected synthetic app credentials. Existing WASMER_TOKEN is not retrieved or repurposed as app authentication. No new credentials or paid resources were provisioned.
