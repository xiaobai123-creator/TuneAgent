# Test audio attribution

The preferred `test-tone-3s.mp3` file is a short 440 Hz test tone from
LoremFile. It is used only to verify the download pipeline.

- Work: `sine-440hz-3s.mp3`
- Attribution: LoremFile sample MP3
- Source page: https://loremfile.dev/mp3
- Direct file: https://loremfile.dev/mp3/sine-440hz-3s.mp3
- License: CC0 1.0 Universal
- License text: https://creativecommons.org/publicdomain/zero/1.0/

The script writes a machine-readable manifest next to the downloaded file with
the source URL, license, size, SHA-256 digest, and download time.

## Generated fallback

If the LoremFile host cannot be reached, the script generates
`test-silence.wav` locally instead. The fallback contains one second of digital
silence and no third-party copyrighted content. Its manifest records
`source_kind: generated`.
