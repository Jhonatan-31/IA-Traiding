#!/usr/bin/env bash
# Formatea /dev/sda2 (HITACHI) como ext4, monta en /srv/backups y crea áreas separadas.
# DESTRUCTIVO sobre sda2. Requiere root (nsenter/docker privileged o sudo).
set -euo pipefail

DISK_PART="${DISK_PART:-/dev/sda2}"
MOUNT_POINT="${MOUNT_POINT:-/srv/backups}"
LABEL="${LABEL:-EBZ-BACKUPS}"
OWNER_USER="${OWNER_USER:-adminebz}"
OWNER_GROUP="${OWNER_GROUP:-adminebz}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: ejecutar como root" >&2
  exit 1
fi

if [[ ! -b "$DISK_PART" ]]; then
  echo "ERROR: no existe $DISK_PART" >&2
  exit 1
fi

if findmnt -n -S "$DISK_PART" >/dev/null 2>&1; then
  echo "ERROR: $DISK_PART ya está montado; desmontar antes" >&2
  findmnt -S "$DISK_PART" || true
  exit 1
fi

# Seguridad: no tocar el NVMe del sistema
ROOT_SRC=$(findmnt -n -o SOURCE / || true)
if [[ "$ROOT_SRC" == *"$DISK_PART"* ]]; then
  echo "ERROR: $DISK_PART parece ser el root — abortando" >&2
  exit 1
fi

echo "== wipefs + mkfs.ext4 $DISK_PART label=$LABEL =="
wipefs -a "$DISK_PART"
mkfs.ext4 -F -L "$LABEL" "$DISK_PART"

UUID=$(blkid -s UUID -o value "$DISK_PART")
echo "UUID=$UUID"

mkdir -p "$MOUNT_POINT"
if ! grep -qE "[[:space:]]$MOUNT_POINT[[:space:]]" /etc/fstab; then
  echo "UUID=$UUID $MOUNT_POINT ext4 defaults,nofail,x-systemd.device-timeout=10 0 2" >> /etc/fstab
  echo "fstab: entrada añadida"
else
  echo "fstab: $MOUNT_POINT ya existía — no duplicar"
fi

mount "$MOUNT_POINT"
df -hT "$MOUNT_POINT"

mkdir -p \
  "$MOUNT_POINT/ia-bot-trading" \
  "$MOUNT_POINT/consultate" \
  "$MOUNT_POINT/scripts" \
  "$MOUNT_POINT/lost+found"

chown -R "$OWNER_USER:$OWNER_GROUP" \
  "$MOUNT_POINT/ia-bot-trading" \
  "$MOUNT_POINT/consultate" \
  "$MOUNT_POINT/scripts"

chmod 750 "$MOUNT_POINT/ia-bot-trading" "$MOUNT_POINT/consultate"
chmod 755 "$MOUNT_POINT" "$MOUNT_POINT/scripts"

cat > "$MOUNT_POINT/README.txt" <<EOF
EBZ backup disk ($LABEL)
Montaje: $MOUNT_POINT
UUID: $UUID
Áreas:
  ia-bot-trading/  — dumps PostgreSQL paper (stack ia-bot-trading)
  consultate/      — dumps MySQL Consultate (mediconnect)
Scripts: $MOUNT_POINT/scripts/
EOF
chown "$OWNER_USER:$OWNER_GROUP" "$MOUNT_POINT/README.txt"

echo "OK mount=$MOUNT_POINT uuid=$UUID"
