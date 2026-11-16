# Controlled Real Download

TuneAgent's default mode remains offline Mock mode. Real downloading is opt-in
and requires the user's own Netease `MUSIC_U` cookie.

## Scope and compliance

- Use only an account and cookie that you own and are authorized to use.
- Download only tracks the account can legitimately access.
- Do not bypass VIP, regional, copyright, DRM, or other access restrictions.
- Do not redistribute downloaded audio or commit cookies/downloads to Git.
- Respect Netease's terms of service, rate limits, and local copyright law.

The downloader never logs the cookie or the resolved audio URL. It requests
standard-quality MP3 only, writes audio atomically, and records a sidecar
manifest without credentials.

## Cookie configuration

Preferred option: create a protected cookie file.

```bash
cd /root/agent-project
printf 'MUSIC_U=%s\n' '<your MUSIC_U value>' > .netease_cookie
chmod 600 .netease_cookie
```

Alternative environment variables:

```bash
export NETEASE_MUSIC_U='<your MUSIC_U value>'
```

or:

```bash
export NETEASE_COOKIE='MUSIC_U=<value>; __csrf=<optional value>'
```

Environment values take precedence over `.netease_cookie`.

## Commands

Real search only:

```bash
python scripts/run_cli.py '国风 按热度 前15' --real
```

Search and download one explicitly selected song:

```bash
python scripts/run_cli.py '国风 按热度 前15' --real --download-song-id <song-id>
```

Download one song without running a new search:

```bash
python scripts/run_cli.py --real --download-song-id <song-id>
```

The optional dependency is installed with:

```bash
python -m pip install -e '.[real]'
```
