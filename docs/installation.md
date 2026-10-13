# Installation

The verified target is AYN Thor with the Thorch BSP, InputPlumber and KWin.

Download a package from Releases and install it:

```sh
sudo pacman -U handhelddash-VERSION-any.pkg.tar.zst
sudo systemctl enable --now inputplumber.service aynthor-hardwared.service
systemctl --user enable --now aynthor-control.service
```

Launch with `handhelddash`, or press AYN to toggle the panel. Settings remain available through `handhelddash --settings`.

## Build the current checkout

```sh
bash scripts/build-package.sh --noconfirm
```

Run the builder as a normal user. See [project structure](portability.md) for package deployment.

Upgrades preserve user preferences. Manually installed service overrides may take precedence over packaged units.

Android userdata access requires a separately provisioned, matching kernel and unlock backend.
