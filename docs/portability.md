# Project structure

`src/app.py` and `src/daemon.py` are startup entrypoints.

Runtime modules live under `src/handhelddash/`:

- `ui/`: pages, widgets and state presentation.
- `services/`: application operations, storage, monitoring and communication.
- `desktop/`: generic, KWin and Plasma adapters.
- `integrations/inputplumber/`: controller profiles and feedback.
- `integrations/thorch/`: board-support commands and hardware control.
- `devices/`: device discovery and profiles.

Hardware backends implement a shared contract. Desktop capabilities determine available actions. New integrations extend these boundaries and preserve the public D-Bus API.

AYN Thor with KWin is the verified target. Other devices and desktops require their own adapters and validation.

## Development deployment

```sh
bash scripts/build-package.sh --noconfirm
bash scripts/deploy-package.sh build/packages/handhelddash-1.2.0-3-any.pkg.tar.zst root@DEVICE SESSION_USER
```

Deployment uses pacman packages. About displays the installed version and build identity. Diagnostic records remain outside the repository and release package.
