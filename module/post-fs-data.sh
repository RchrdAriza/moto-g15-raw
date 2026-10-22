#!/system/bin/sh
# Bind-mount the patched library before camerahalserver starts. Disabling/removing the module undoes it.
MODDIR=${0%/*}
T=/vendor/lib64/libmtkcam_metastore.so
P=$MODDIR/files/libmtkcam_metastore.so
STOCK=d4d71c54fbf12a925313ed166c793c48d433c550006a7fc0c6d3de3836f09b13
PATCHED=d6fc9c33a7850eef7d3a1c3a23e610b722adf324c2cea9e9c559bdcf414f5ba3
LOG=$MODDIR/last-boot.log
{
  [ "$(sha256sum $T | cut -d' ' -f1)" = "$STOCK" ] || { echo "stock hash mismatch; skipped"; exit 0; }
  [ "$(sha256sum $P | cut -d' ' -f1)" = "$PATCHED" ] || { echo "patched hash mismatch; skipped"; exit 0; }
  chcon u:object_r:vendor_file:s0 $P
  mount -o bind $P $T && echo "mounted: $(sha256sum $T)"
} > $LOG 2>&1
