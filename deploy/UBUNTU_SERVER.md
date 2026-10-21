# Separate Ubuntu Server ordering

## Scope

Adds `Ubuntu Server 26.04` as a separate stored OS identifier, displayed as
**Ubuntu Server 26.04 LTS**. The owner reports a desktop UI in the existing Ubuntu
template; its stored identifier stays `Ubuntu 26.04`, displayed as
**Ubuntu Desktop 26.04 LTS**. Existing orders, default OS, provisioning payloads,
template mappings and customer VMs are not rewritten or converted.

Status: prepared locally; no new template, production migration or deployment
is established by this runbook. Do not advertise the Server option until both
applications and the actual template have passed acceptance.

## Configuration and rollout order

1. Inspect the current Proxmox VM inventory and storage. Choose a new unused
   template VMID; do not reuse or edit the Desktop, Debian or Windows templates.
2. Build a separate template using Canonical's released
   `ubuntu-26.04-server-cloudimg-amd64.img` and verify its SHA256 against the
   matching official checksum file before import. Source:
   <https://cloud-images.ubuntu.com/releases/resolute/release/>. Pin and record
   the downloaded image's digest/build; a mutable release URL alone is not a
   reproducible image identity.
3. Before customer availability, verify the new image boots without a desktop,
   supports cloud-init, has a functioning QEMU Guest Agent, grows its disk, and
   receives the intended user/network/SSH-key configuration. Test only a fresh
   disposable clone with a reviewed isolated network and unused identity.
   Do not attach a clone to a production bridge with an arbitrary address or
   assume the image contains an operational guest agent.
4. Deploy the matching provisioner change first. Configure its private process
   environment with `VPS_TEMPLATE_UBUNTU_SERVER_26_04_VMID` set to the verified
   new VMID. An absent value leaves Server unsupported; invalid, nonpositive
   or reused template IDs refuse startup. The provisioner must never silently
   fall back to the existing Desktop template.
5. Deploy the portal change while keeping
   `UBUNTU_SERVER_ORDERING_ENABLED=False`. Migration
   `0013_ubuntu_server_operating_system` depends on deployed accounts migration
   `0012_customer_accounts`; it changes Django field choices/labels only, not
   existing order values. Inspect the actual migration plan and retain rollback
   source/environment copies before rollout. Combining the separate pending
   renewal branch requires migration graph reconciliation.
6. Verify the VM100 template selector and one controlled end-to-end Server
   provisioning flow before enabling `UBUNTU_SERVER_ORDERING_ENABLED=True` on
   the portal. A supported operator-controlled test path must not expose the
   option to other customers before acceptance. Existing test-payment settings
   remain unchanged; do not create real charges merely to check the selector.

The public checkout hides Server and rejects crafted submissions while disabled.
The order-confirmation service also refuses new Server orders when disabled.
Existing confirmed token retries remain idempotent. Existing paid orders retain
their OS even if new ordering is later disabled.

## Acceptance

- Existing Desktop, Debian and Windows choices retain their stored identifiers
  and mappings. Windows and Server ordering switches are independent.
- Server checkout requires a Linux SSH public key; posted resource/OS overrides
  cannot replace the reviewed order configuration.
- A paid Server order reaches VM100 with the exact Server identifier and clones
  the new template. Repeating the same order does not create another guest.
- Confirm actual OS/build, no desktop session, agent/network readiness, disk
  growth and customer SSH access on the disposable clone. No actual live
  acceptance is implied by mocked application tests.

## Recovery

Disable new Server ordering first if provisioning acceptance fails. Retain
existing order/guest identities and investigate ambiguous results; do not retry
cloning with a fresh order ID. Keep the Server mapping for any outstanding paid
orders until reviewed. Template deletion, migration reversal and customer VM
conversion are not part of routine recovery. Existing Desktop remains intact.
