#!/system/bin/sh
# Undo apply.sh without rebooting.
T=/vendor/lib64/libmtkcam_metastore.so
setprop ctl.stop camerahalserver; sleep 1
while grep -q " $T " /proc/mounts; do umount $T || umount -l $T || break; done
setprop ctl.start camerahalserver
echo "rolled back: $(sha256sum $T)"
