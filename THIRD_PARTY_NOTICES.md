# Third-party notices

Shiyan WeChat uses `wechatauto-replica` version 1.2.4.1 for local WeChat database access.

- Project: https://github.com/fanyuantaier/wechatauto-replica
- Author / maintainer: fanyuantaier and the upstream contributors
- License: Apache License, Version 2.0
- License copy: `licenses/wechatauto-replica-LICENSE`

The dependency is installed through pip and is not vendored into this repository. Shiyan provides its own Tkinter interface and streaming export adapter. Shiyan's source files are licensed under MIT; dependencies retain their respective licenses.

The upstream database API contains private methods used by this adapter. Keep the pinned dependency version until changes have been tested.
