# Security

AI Incident Lab is a local simulation and evaluation environment. The control API has no production authentication. Keep its ports bound to localhost; do not expose it directly to the internet.

## Credentials and local data

Store provider credentials and agent registration tokens in environment variables or your ignored local `.env`. `.env.example` contains names and empty values only. Registration tokens are shown once; the registry stores their hashes. Rotate tokens in the UI if exposed.

Local databases, reports, logs, and browser artifacts may contain diagnostic data or text submitted by agents. Treat them as private. Browser traces are disabled and CI does not upload raw execution artifacts, since HTTP registration responses contain tokens. Ignore rules and automated scans reduce accidental publication but cannot guarantee that arbitrary agent-generated text is free of secrets.

Do not include real keys, tokens, private keys, or personal account details in commits or issue reports. If a credential was published, revoke or rotate it first; deleting a file or rewriting Git history does not invalidate a credential or remove copies held elsewhere.

## Reporting

Use GitHub private vulnerability reporting if enabled on this repository. Otherwise, open an issue requesting a private reporting channel without including exploit details, credentials, or private data. Do not publish sensitive material in a public issue.

Security fixes target the current main branch; no separate long-term support branches are maintained.
