# Notice regarding `module/files/libmtkcam_metastore.so`

That file is **not** covered by this repository's MIT license.

It is a modified copy of `libmtkcam_metastore.so`, a proprietary camera HAL library by
MediaTek, as shipped by Motorola in the Moto G15 (`lamu`) vendor image, build `VVTA35.51-153`.
All rights to the original work belong to their respective owners. It is included here only so
that owners of this device can install the module without first extracting and patching their own
copy.

The modification consists of 20 changed bytes and a 112-byte code cave, documented in full in the
README and implemented in `make_patch.py`. No part of the library was decompiled into source, and
nothing of it is reproduced in this repository's own source files.

**You can avoid the redistributed binary entirely.** `make_patch.py` produces a byte-identical
result from the library already present on your own device:

```sh
adb shell su -c 'cat /vendor/lib64/libmtkcam_metastore.so' > stock.so
python3 make_patch.py stock.so module/files/libmtkcam_metastore.so
```

If you are a rights holder and object to this file being distributed here, open an issue and it
will be removed; the repository remains fully functional without it.
