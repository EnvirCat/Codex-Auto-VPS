# Security Policy

## Secrets

Do not commit:

- SSH private keys
- VPS passwords
- panel credentials
- residential proxy credentials
- generated subscription URLs
- handoff files with live IPs, UUIDs, passwords, or tokens

## Reporting

If you find a workflow that accidentally encourages leaking credentials or leaving unsafe services exposed, please open an issue with a redacted example.

## Operational Guidance

- Keep VPSes independent unless explicitly required.
- Disable unused panels and compatibility services.
- Use firewall default-deny inbound rules.
- Rotate node credentials and subscription paths when exposure is suspected.
- Prefer key-based SSH and disable password authentication on production hosts.
