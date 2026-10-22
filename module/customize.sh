# Refuse to install on a vendor build this patch was not made for.
# The patched hash is accepted too, for when apply.sh's RAM-only mount is currently active.
STOCK=d4d71c54fbf12a925313ed166c793c48d433c550006a7fc0c6d3de3836f09b13
PATCHED=d6fc9c33a7850eef7d3a1c3a23e610b722adf324c2cea9e9c559bdcf414f5ba3
H=$(sha256sum /vendor/lib64/libmtkcam_metastore.so | cut -d' ' -f1)
[ "$H" = "$STOCK" ] || [ "$H" = "$PATCHED" ] || abort "! vendor libmtkcam_metastore.so is not the expected build (VVTA35.51-153); not installing"
set_perm "$MODPATH/files/libmtkcam_metastore.so" 0 0 0644 u:object_r:vendor_file:s0
ui_print "- RAW16 unlock installed; active after reboot"
