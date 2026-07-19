# Security Policy

Telecraft handles Telegram authorization material and should be treated as security-sensitive
software. Please report suspected vulnerabilities privately.

## Supported versions

| Release line | Security support |
| --- | --- |
| Latest stable minor release | Supported |
| Previous stable minor release | Critical fixes for 90 days after the next minor release |
| Latest public beta or release candidate, when no stable release exists | Reports accepted; fixes are best-effort |
| Older prereleases and internal `0.1.x` builds | Not supported |

The current supported stable line is `0.2.x`. Prereleases may change before their corresponding
stable release; that does not reduce the priority of a security report.

## Report a vulnerability

Use GitHub's private vulnerability reporting form:

<https://github.com/meniwap/telecraftor/security/advisories/new>

Do not open a public issue and do not include a real session file, `auth_key`, API hash, bot token,
login code, phone number, private message, or unredacted diagnostic output. A useful report includes:

- affected Telecraft and Python versions;
- impact and prerequisites;
- minimal, synthetic reproduction steps or a redacted proof of concept;
- whether the issue affects user sessions, bot sessions, or both;
- any known workaround.

If the private form is unavailable, use the
[private-contact request form](https://github.com/meniwap/telecraftor/issues/new?template=security_contact.yml).
Submit only the category of request and no vulnerability details. A maintainer will establish a
private channel.

## Response and disclosure

The project aims to:

- acknowledge a report within 3 business days;
- provide an initial severity and scope assessment within 7 business days;
- send an update at least every 14 days while remediation is active.

These are response targets, not a guarantee that every issue can be fixed within a set period.
Reporter and maintainer should coordinate publication. Please avoid disclosure until a fix and
advisory are available. The default target is disclosure within 90 days, adjusted when active
exploitation, user safety, upstream coordination, or release availability requires a different
timeline. Credit is offered unless the reporter asks to remain anonymous.

## High-value local data

Session files contain a plaintext MTProto `auth_key`; possession can permit account access. File
permissions are only a best-effort control, not encryption. See [the detailed threat model](docs/security.md)
before operating a real account or collecting live-test artifacts.
