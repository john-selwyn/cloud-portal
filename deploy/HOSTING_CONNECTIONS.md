# Customer SSH/SFTP details

Prepared from portal `9658e52` and Hestia 1.10.5. No production rollout is performed by these files.

## Cloud Portal

Adds `/my-hosting/` and owner-scoped, password-free downloadable welcome instructions. Customers see their mapped Hestia username, primary domain folder, public endpoint, server fingerprint and only the commands enabled by the recorded shell. Copy buttons fail gracefully when browser clipboard access is unavailable. Nothing sends email or changes Hestia permissions.

The additive migration `0014_hosting_account_connections` creates `HostingAccount`. A superuser must map each existing account to the verified customer, Hestia username, primary domain, package, actual shell and verification timestamp in Django admin. There is no automatic match by email/portal username and no production data is seeded. Record additional/custom document roots separately; the displayed primary-domain folder is the standard Hestia layout.

Before release, capture the actual VM200 source, local changes and migration graph. Reconcile any newer release/migration conflicts rather than blindly applying this older baseline. Back up the portal database, inspect `migrate --plan`, rehearse on an isolated copy, then deploy the reviewed source using the existing production environment, migrate, collect static files and restart the intended service. Confirm runtime revision and customer ownership with two accounts. The portal mail feature remains unchanged.

Optional environment settings:

```dotenv
HOSTING_ACCESS_HOST=proxmo-2.dyndns.org
HOSTING_ACCESS_PORT=2222
HOSTING_ACCESS_FINGERPRINT=SHA256:Rq1n3VqFXEybay61onqtGlH1SC6bKQ5NyQ1Ub4xwOIc
```

Rollback: revert the feature source and navigation while retaining the additive table. Do not reverse the migration if mappings must be preserved. No Hestia account, password, router or SSH daemon settings are changed.

## Hestia panel

The card is inserted on the authenticated **Web Domains** page. It uses Hestia's current username, effective shell and domain list; administrators see it only while viewing a customer account. All dynamic values are escaped. No passwords, private keys, new privileged commands or standalone unauthenticated PHP routes are introduced.

Hestia overwrites templates during updates. `hestia-connections/install.py` verifies the exact reviewed 1.10.5 template before making changes, backs it up, installs scoped assets and appends an owned block to the existing post-install hook. Unfamiliar templates/hook interpreters stop installation. After an upstream template change, the hook stops for review rather than overwriting the new template.

Transfer the reviewed `hestia-connections/` folder to a private administrator staging directory on **10.50.0.24**. Inspect the installed version, existing Web Domains template and update hook first. Then, from that folder:

```bash
sudo python3 install.py
sudo python3 install.py --apply
```

The first command only checks the template. Apply also runs Hestia's bundled PHP syntax checker before modifying it. No service restart is needed. Verify the Web Domains screen as Starter, Business/Pro and administrator, including admin impersonation, dark/light themes and mobile layout. Confirm copy buttons and existing domain actions.

Rollback:

```bash
sudo python3 /usr/local/share/ict-hosting-ui/install.py --remove
```

This removes only the owned include/hook block and retains backups/assets. It refuses an unfamiliar template. Existing custom hooks are preserved. Review and test an upstream update before calling update persistence accepted.

## Welcome delivery

The download on My hosting is ready for the verified customer to retrieve. Staff can use the same password-free wording during an approved onboarding workflow. Email is not sent automatically, because hosting provisioning/mail acceptance is not yet implemented. Deliver initial credentials using the existing protected handover process, not this template.

## Scope of existing access tests

The owner confirmed SSH and SFTP login/directory listing over a mobile-data hotspot using `proxmo-2.dyndns.org:2222`. Starter remains `nologin`; Business/Pro use `jailbash`. This feature displays those details; it does not expand access. Upload/download, full tenant isolation, a new customer's package inheritance and live feature rollout require their own checks.
