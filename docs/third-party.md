# Licensing and provenance / 授权与来源

Original HandheldDash application, daemon, packaging and documentation:
Copyright (c) 2026 lurenjiamax, LGPL-3.0-or-later. LICENSE contains the LGPL
additional permissions, and COPYING contains the incorporated GPLv3 terms.
本项目原创代码及文档采用 LGPL-3.0-or-later。

lpunpack: https://github.com/Unix3dgforce/lpunpack, revision
c59b8f3b069c5a8aa438a049fa4a091177172434. Vendored without modification under
LGPLv3; see vendor/lpunpack/LICENSE.md and its README for provenance.

Lucide icons: https://lucide.dev, ISC; see packaging/icons/LICENSE-lucide.
Icons are supplied as SVGs with the original notice.

PyQt6 is an external runtime dependency under GPLv3 or Riverbank commercial
licensing. Other system dependencies keep their own licenses. LGPL licensing
of HandheldDash's original files does not replace dependency requirements or
guarantee that every combined redistribution can be treated as LGPL-only.
PyQt6 等依赖保留原授权；本项目 LGPL 声明不替代依赖的许可义务。

Thorch board-support tools are external dependencies and are not included or
relicensed here. Their upstream source is GPL-2.0-or-later unless otherwise
specified: https://github.com/ROCKNIX/distribution. No kernel, firmware, device
image, extracted Android data or research artifacts are shipped.

Audio-response design was informed by WLED audio-reactive and LedFx adaptive
normalization. The project contains its own small implementation, not copied
WLED/LedFx code: https://github.com/wled/WLED/tree/main/usermods/audioreactive
and https://github.com/LedFx/LedFx/tree/main/ledfx/effects.
