Vendored from https://github.com/Unix3dgforce/lpunpack
Revision: c59b8f3b069c5a8aa438a049fa4a091177172434
License: LGPL v3; see LICENSE.md. Source is unmodified.

Used to read Android super metadata and extract selected logical partitions.
The daemon uses the metadata reader directly because the CLI JSON summary
pairs partition sizes incorrectly when empty B-slot entries exist.
