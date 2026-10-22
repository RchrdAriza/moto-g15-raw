#!/system/bin/sh
# Temporary (RAM-only) RAW patch for Moto G15 lamu camera HAL.
# Bind-mounts a patched libmtkcam_metastore.so over /vendor; reboot or rollback.sh undoes it.
set -e
T=/vendor/lib64/libmtkcam_metastore.so
DIR=/data/local/tmp/rawtest
P=$DIR/patched.so
ORIG=d4d71c54fbf12a925313ed166c793c48d433c550006a7fc0c6d3de3836f09b13
PATCHED=d6fc9c33a7850eef7d3a1c3a23e610b722adf324c2cea9e9c559bdcf414f5ba3
grep -q " $T " /proc/mounts && { echo "already mounted; run rollback.sh first"; exit 1; }
[ "$(sha256sum $T | cut -d' ' -f1)" = "$ORIG" ] || { echo "vendor lib is not the expected build; aborting"; exit 1; }
cp -f $DIR/stage.so $P
[ "$(sha256sum $P | cut -d' ' -f1)" = "$PATCHED" ] || { echo "patched lib hash mismatch; aborting"; exit 1; }
chown root:root $P; chmod 0644 $P; chcon u:object_r:vendor_file:s0 $P
setprop ctl.stop camerahalserver; sleep 1
mount -o bind $P $T
setprop ctl.start camerahalserver
echo "applied: $(sha256sum $T)"
