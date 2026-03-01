# Security

How yreflow handles your credentials and connection to Wolfery.

## Authentication Flow

yreflow uses a two-step process:

1. **First login** -- You enter your username and password in the login screen. The password is hashed client-side and sent over HTTPS to Wolfery's auth server. If successful, the server returns an auth token.
2. **Subsequent launches** -- The token is reused automatically. No password prompt unless the token expires.

## Password Handling

Your password is **never stored** on disk. When you log in:

- The password is hashed with SHA-256 and HMAC-SHA-256 before leaving your machine.
- The hashes are sent over HTTPS (`https://auth.mucklet.com/login`).
- The plaintext password exists only briefly in memory during the hashing step.

## Token Storage

After a successful login, the auth token is saved to:

```
~/.config/yreflow/config.toml
```

The token is stored as **plaintext** in this file. It is protected only by your operating system's file permissions. Anyone with read access to your home directory could read it.

To remove a stored token, delete the `token` line from your config file or delete the file entirely.

## Transport Security

All network traffic uses TLS:

- **Authentication**: HTTPS to `auth.mucklet.com`
- **WebSocket**: WSS (TLS-encrypted) to `api.wolfery.com`

No data is sent over unencrypted connections.

## Token Expiry

When a token expires, yreflow automatically clears it from the config file and shows the login screen again. No manual intervention is needed.

## Log Files

yreflow logs all WebSocket traffic (incoming and outgoing messages) to daily log files. These logs may contain private content such as whispers, pages, and roleplay messages.

Default location:

```
~/.config/yreflow/logs/
```

One file per day, named `YYYY-MM-DD.log`.

To change the log directory, set `log_dir` in your config file:

```toml
log_dir = "/path/to/your/logs"
```

Treat these files as sensitive. They are not encrypted and anyone with read access to the directory can view them.

The intention is to discontinue this use after alpha phase.

## What Is Not Stored

- Passwords (never written to disk)
- Other users' credentials or personal data
