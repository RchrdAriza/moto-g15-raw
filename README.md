# Moto G15 (lamu) — RAW16 unlock

Motorola ships the Moto G15 with RAW capture disabled in the camera HAL. Android's camera service
reports no `RAW` capability and no RAW stream on any camera, which is why **Google Camera ports
crash** on this device — GCam's HDR+ pipeline needs Bayer RAW frames and the HAL never offers any.

The hardware and the MediaTek HAL both support RAW. It was switched off in Motorola's per-sensor
metadata. This module turns it back on.

| Camera | Sensor | Before | After |
|---|---|---|---|
| 0 (rear main) | S5KJNSSQ | no RAW | **RAW16 4080×3072**, GBRG |
| 1 (front) | SC820CS | no RAW | **RAW16 3264×2448**, BGGR |
| 2 (rear aux) | SC520CS | no RAW | unchanged |

With the module active, **GCam works**: LMC 8.4 R18F1 opens both cameras with the RAW16 stream and
saves HDR+ JPEGs without crashing.

> **Scope:** this changes what the camera HAL advertises to apps. It does not touch the radio,
> the bootloader or anything outside `/vendor/lib64/libmtkcam_metastore.so`, and it is applied as a
> bind mount — the real partition is never written.

---

## Compatibility

Built and verified against exactly one vendor build:

| | |
|---|---|
| Device | Moto G15 `lamu` (XT2521-2), MediaTek MT6768 |
| Vendor | `VVTA35.51-153` |
| Target file | `/vendor/lib64/libmtkcam_metastore.so` |
| Stock sha256 | `d4d71c54fbf12a925313ed166c793c48d433c550006a7fc0c6d3de3836f09b13` |
| Patched sha256 | `d6fc9c33a7850eef7d3a1c3a23e610b722adf324c2cea9e9c559bdcf414f5ba3` |
| Tested on | LineageOS 24.0 (Android 17), KernelSU 3.3.1 |

**The module refuses to install or mount if your stock library hash differs.** On a different
vendor build, regenerate the patch from your own blob — see [Building from your own blob](#building-from-your-own-blob).
Other `lamu` variants and other MediaTek devices will need different offsets.

Requires root (KernelSU or Magisk).

## Install

1. Download `moto_g15_raw_v4.zip` from [Releases](../../releases).
2. Flash it in the KernelSU or Magisk app.
3. Reboot.
4. Check it worked:
   ```
   adb shell dumpsys media.camera | grep -A1 'availableCapabilities'
   ```
   Cameras 0 and 1 should now list `RAW`.

The module bind-mounts the patched library from `post-fs-data.sh`, before `camerahalserver`
starts, so no HAL restart is needed. It verifies both hashes first and does nothing on a mismatch —
after a vendor OTA it will simply stay inactive instead of breaking your camera.

Log: `/data/adb/modules/moto_g15_raw/last-boot.log`

**To revert:** disable or remove the module and reboot. Nothing persists.

> If the module seems to do nothing on boot, check that `/data/adb/ksud` matches your kernel's UAPI
> version (`ksud -V`). An outdated `ksud` silently skips all boot scripts. Opening the KernelSU app
> updates it.

## Using it with GCam

Any port with a RAW format selector works. [LMC 8.4 R18F1](https://www.celsoazevedo.com/files/android/google-camera/dev-hasli/)
was the one verified here — it has every knob this device needs and modest library size, which
matters on 4 GB of RAM.

Settings that matter:

| Setting | Value | Why |
|---|---|---|
| RAW format | **RAW16** | the HAL only exposes RAW16, not RAW10 |
| Hexagon DSP | **off** | that's Qualcomm hardware; this is MediaTek |
| Black level | **64** | the sensor's actual black level |

The HAL allows **one open camera at a time**, so GCam features that open two cameras simultaneously
will not work.

## Temporary testing without installing the module

`scripts/apply.sh` does the same bind mount from a shell. It lasts until reboot — useful while
testing a rebuilt patch.

```sh
adb shell mkdir -p /data/local/tmp/rawtest
adb push module/files/libmtkcam_metastore.so /data/local/tmp/rawtest/stage.so
adb push scripts/apply.sh scripts/rollback.sh /data/local/tmp/rawtest/
adb shell su -M -c sh /data/local/tmp/rawtest/apply.sh      # apply now
adb shell su -M -c sh /data/local/tmp/rawtest/rollback.sh   # undo now
```

## Building from your own blob

`make_patch.py` takes your device's stock library and produces the patched one. It verifies the
input hash and every byte it rewrites, so it fails loudly rather than producing a broken library.

```sh
adb shell su -c 'cat /vendor/lib64/libmtkcam_metastore.so' > stock.so
python3 make_patch.py stock.so module/files/libmtkcam_metastore.so
```

## How it works

Three pieces of MediaTek's HAL are involved:

1. `constructCustStaticMetadata_PLATFORM_PROJECT_SENSOR_DRVNAME_<sensor>_MIPI_RAW` — Motorola's
   per-sensor override. It builds `availableCapabilities` (tag `0xc000c`) as `[0 1 2 5 6 9]` for the
   rear camera. MediaTek's own default (`DEVICE_REQUEST_COMMON`) is `[0 1 2 5 3 6]` — it *includes*
   `RAW` (3). So RAW was removed by the OEM, not missing from the platform.
2. The same function builds the stream candidate list (tag `0xd001c`) with only `BLOB` (33) and
   `YUV_420_888` (35) entries.
3. `MetadataProvider::updateRawCapability()` fills in the rest of the RAW metadata — but only if
   `RAW` is already declared, and it only *resizes* existing RAW16 stream entries, never creates
   them.

So two things have to change: declare the capability, and provide one RAW16 stream entry for
`updateRawCapability()` to fix up.

**The patch, 20 bytes plus a 0x70-byte code cave:**

| # | Site | Change |
|---|---|---|
| 1 | `0x2f02c` | `mov w8,#9` → `mov w8,#3` — rear caps become `[0 1 2 5 6 3]` |
| 2 | `0x31f88`, `0x31f9c`, `0x31fb0` | rear stream candidate #44 (`BLOB 1024×768`) → `RAW16 4080×3072` |
| 3 | `0x36880` | front caps: the last `push_back` is redirected through a cave that pushes `6` itself and leaves `3` for the original call → `[0 1 2 5 6 3]` |
| 4 | `0x37b34`, `0x37b48`, `0x37b5c` | front stream candidate #21 (`BLOB 1024×768`) → `RAW16 3264×2448` |

The caves live in the zero padding after `.plt` (`0x65de0`–`0x65e48`); the executable `PT_LOAD` is
grown by `0x70` to cover them, within the same page, so the file layout is unchanged.

The rear camera's capability list had a spare slot (`9` = `CONSTRAINED_HIGH_SPEED_VIDEO`) that could
be overwritten in place. The front camera's list had none, hence the cave trick for #3.

**Cost of the patch:**
- the rear camera loses `CONSTRAINED_HIGH_SPEED_VIDEO` (slow motion);
- both cameras lose the 1024×768 JPEG size;
- the rear aux camera is untouched.

## Verified results

Measured on-device with `tools/rawprobe` (a small camera2 NDK probe, see below):

| Test | Result |
|---|---|
| Rear RAW16 4080×3072 | 13.3 fps sustained |
| Rear RAW16 + 1080p YUV preview | 13.25 fps on both streams |
| Front RAW16 3264×2448 | 14.8 fps (also with preview) |
| Rear data sanity | GBRG, black level 64 (0.1st percentile = 64), white 1023, both G sites match, lens vignetting visible |
| Front data sanity | BGGR, matching G sites |
| GCam LMC 8.4 R18F1 | rear and front both open with RAW16, HDR+ JPEGs saved, no crash |
| Rollback | stock hash restored; stock library + same probe still works (control) |

RAW runs at ~13–15 fps versus ~20 fps for YUV, because the HAL serves it through MediaTek's DNG
path. Fast enough for HDR+ bursts; the viewfinder feels slightly slower.

## Tools

**`tools/rawprobe/rawprobe.c`** — a standalone camera2 NDK probe that opens a camera with a RAW16
stream (optionally plus a YUV preview stream), measures the steady-state frame rate, dumps one
frame, and prints per-CFA-site means so you can tell real Bayer data from garbage. Useful for
verifying a RAW patch without involving a camera app.

```sh
NDK=~/Android/Sdk/ndk/<version>
$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android34-clang \
    -O2 -Wall -o rawprobe rawprobe.c -lcamera2ndk -lmediandk -ldl
adb push rawprobe /data/local/tmp/
adb shell su -M -c '/data/local/tmp/rawprobe 0 4080 3072 /data/local/tmp/f.raw16 raw16 +preview'
```

**`tools/mtk_meta_trace.py`** — traces MediaTek `IMetadata::IEntry` construction in `llvm-objdump`
output: for each metadata tag built, it prints the values pushed into it and the instruction
address that materialises each one. That address is what you patch. This is how every offset above
was found, and it should work on any MediaTek `libmtkcam_metastore.so`.

```sh
llvm-objdump -d libmtkcam_metastore.so | c++filt > dump.dis
python3 tools/mtk_meta_trace.py dump.dis all          # every tag
python3 tools/mtk_meta_trace.py dump.dis 0xc000c      # just availableCapabilities
```

## Licensing

The scripts and tools here (`make_patch.py`, `tools/`, `scripts/`, `module/*.sh`) are MIT licensed —
see [LICENSE](LICENSE).

`module/files/libmtkcam_metastore.so` is **not** mine: it is a patched copy of a proprietary
MediaTek/Motorola vendor library, included for convenience. See [NOTICE.md](NOTICE.md). If you would
rather not use a redistributed blob, build your own with `make_patch.py` — it produces a
byte-identical result from your device's own library.

## Disclaimer

Use at your own risk. This has been tested on one device and one vendor build. The hash checks make
a silent mismatch unlikely, and the module is a bind mount you can disable, but no warranty of any
kind is given.
