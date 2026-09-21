# Rehearsals

Real runs (containers, real-data copies) kept as scripts so they can be repeated
and quoted. Each one works in throwaway containers, volumes and directories,
never touches the running application, `.env` or `data/`, removes what it
created, and prints the numbers to quote in an issue. Run them from the
repository root. They need Docker (except `rekey_rehearsal.sh`) and a built
`.venv`.

| Script | Checks | Issue |
|---|---|---|
| `container_healthcheck.sh` | image goes `healthy`, then `unhealthy` when frozen | #48 |
| `container_user.sh` | uid, fresh volume, existing data copy, root-owned directory | #70 |
| `tls_proxy.sh` | HTTPS 401/200, plain HTTP, LAN address refused, control | #60 |
| `linux_bind_mount.sh` | non-root image on a real Linux bind mount: root-owned fails with the clear message, chowned 10001 is healthy | #97 |
| `autoheal.sh` | a frozen container is restarted by the autoheal overlay | #89 |
| `ssh_tunnel.sh` | the documented SSH tunnel to the Admin API: 401 / 401 / 200, closed after | #91 |
| `rekey_rehearsal.sh` | `./start.sh --rekey` on a copy of the real data | #78 |

Lessons baked in (see docs/LESSONS.md): explicit `docker run` options (zsh does
not word-split `$VAR`), `-d` plus a bounded wait (never a foreground run of a
process that does not exit), verification before cleanup, the virtualenv's
Python (the system one has no `cryptography`).
