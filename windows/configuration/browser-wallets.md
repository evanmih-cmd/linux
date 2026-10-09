# Verified Chrome Web Store extension identities

Canonical Chrome policy is `ChromeWalletExtensionSettings` in
[`workstation.winget`](workstation.winget). This file is a human-readable
inventory and provenance record, **not** an alternative installer.

These six IDs were checked against publisher-labelled Chrome Web Store
listings on 2026-10-08. Vendor references are shown where available.
Never install extensions by a text search, lookalike domain, ZIP/CRX mirror,
or search-engine advertisement. Installation/update source is solely the Chrome
Web Store official URL `https://clients2.google.com/service/update2/crx`.

| Wallet | Chrome extension ID | Store publisher | Canonical store listing |
|---|---|---|---|
| MetaMask | `nkbihfbeogaeaoehlefnkodbefgpgknn` | Consensys Software Inc. | https://chromewebstore.google.com/detail/metamask/nkbihfbeogaeaoehlefnkodbefgpgknn |
| Phantom | `bfnaelmomeimhlpmgjnjophhpkkoljpa` | Phantom / phantom.com | https://chromewebstore.google.com/detail/phantom/bfnaelmomeimhlpmgjnjophhpkkoljpa |
| Rabby | `acmacodkjbdgmoleebolmdjonilkdbch` | rabby.io | https://chromewebstore.google.com/detail/rabby-wallet/acmacodkjbdgmoleebolmdjonilkdbch |
| Trust Wallet | `egjidjbpglichdcondbcbdnbeeppgdph` | DApps Platform Software Services Ltd. | https://chromewebstore.google.com/detail/trust-wallet/egjidjbpglichdcondbcbdnbeeppgdph |
| Backpack | `aflkmfhebedbjioipglgcbcmnbpgliof` | backpack.app | https://chromewebstore.google.com/detail/backpack/aflkmfhebedbjioipglgcbcmnbpgliof |
| Zerion | `klghhnkeealcohjjanjjdaeeggmfmlpl` | zerion.io | https://chromewebstore.google.com/detail/zerion-wallet-crypto-defi/klghhnkeealcohjjanjjdaeeggmfmlpl |

- Backpack vendor-side link resolved from https://backpack.app/ to the
  listed Chrome Web Store extension.
- Trust Wallet vendor-side link resolved from
  https://trustwallet.com/browser-extension to the listed extension.
- Other sources: https://metamask.io/download,
  https://phantom.app/download,
  https://rabby.io/,
  https://zerion.io/download.
- Policy documentation: https://support.google.com/chrome/a/answer/7532015 ;
  Windows Chrome policies: https://support.google.com/chrome/a/answer/9131254 .

## Installation boundary

`ExtensionSettings` uses `installation_mode: normal_installed`, with the
above exact IDs and Google's update service. The `*` default is `blocked`
for non-listed extensions, limiting the Chrome sensitive-workload browser.
This is **Chrome machine policy**, not a per-profile setting. Normal browsing
uses Edge; Chrome's all-profile policy is intentional. Review before adding
unrelated Chrome usage.

A policy registry key is not proof that extensions have downloaded or loaded.
Acceptance requires a real Chrome profile and `chrome://policy` plus
`chrome://extensions` / managed extension state readback after restart,
including versions, active state, verified IDs, and no unknown extensions.
If Chrome policy is unsupported or not loaded in the target build, do not
silently bypass with downloaded CRX files.

Wallet onboarding/account creation is the owner's responsibility, not part of
unattended configuration. Never import a hardware Ledger seed phrase into
a software wallet. Ledger pairing/signing on physical USB remains an ASUS gate.
Having multiple wallet extensions that inject the default web3 provider may
cause provider collisions; confirm the intended provider on sensitive sites
and use dedicated Chrome profiles where a wallet requires isolation.
