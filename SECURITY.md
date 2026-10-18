# Security policy

## Reporting a vulnerability

Please report it privately through GitHub: open this repository's **Security** tab and choose **Report a vulnerability**. Please don't open a public issue for it.

You'll hear back within a few days. The fix ships in a new release, and the advisory credits you unless you'd rather it didn't.

## Supported versions

Security fixes go into the latest release only.

## Scope

payband-mcp makes outbound requests to public job-board APIs and an exchange-rate feed, and caches the responses on disk. The failures worth reporting are a crafted posting or API response that makes it run code or write outside its cache, and a request sent somewhere you didn't ask it to go.
