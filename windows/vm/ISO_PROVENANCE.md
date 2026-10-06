# Windows 11 ISO provenance

Verified source artifact for the Windows VM bench.

- File: `Windows11_Client_x64_en-us_26300_9457.iso`
- Architecture/language: x64, English (United States)
- Windows build family: 26H2 / 26300.9457
- File size: `9047330816` bytes
- SHA-256: `BD4307DF32BC8AF33B39CCECB1174AEB345386630F89A2B86C7A4E36B55EA650`
- Local source path at verification time: `/home/github-runner/Windows11_Client_x64_en-us_26300_9457.iso`
- Verified: 2026-10-06

Microsoft's Windows 11 download page publishes the same SHA-256 for the current English 64-bit ISO. Microsoft states that an exact SHA-256 match confirms that the ISO has not been corrupted, tampered with, or altered from the original.

The ISO itself is intentionally **not committed to Git**. The bench should reference or copy it into a cache outside the repository and verify this digest before use.
