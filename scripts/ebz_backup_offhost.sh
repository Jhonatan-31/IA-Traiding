#!/usr/bin/env bash
# AG4 — Copia OFF-HOST de backups ya publicados en /srv/backups.
# PREPARADO SIN ACTIVAR: sin OFFHOST_DEST no hace nada (exit 0 con mensaje).
#
# Uso (tras autorización):
#   OFFHOST_DEST=user@host:/path/backups \
#   OFFHOST_MODE=rsync \
#   bash scripts/ebz_backup_offhost.sh
#
# Requisitos: destino externo real, cifrado en tránsito (SSH), checksum verify.
set -euo pipefail
SRC_ROOT="${SRC_ROOT:-/srv/backups}"
OFFHOST_DEST="${OFFHOST_DEST:-}"
OFFHOST_MODE="${OFFHOST_MODE:-rsync}"
LOG="${LOG:-$SRC_ROOT/offhost_sync.log}"

if [[ -z "$OFFHOST_DEST" ]]; then
  echo "PREPARADO_SIN_ACTIVAR: defina OFFHOST_DEST para sincronizar fuera de EBZ."
  exit 0
fi

if [[ ! -d "$SRC_ROOT/ia-bot-trading" ]]; then
  echo "ERROR: falta $SRC_ROOT/ia-bot-trading" >&2
  exit 2
fi

TS=$(date -u +%Y%m%d_%H%M%S)
echo "[$TS] sync start mode=$OFFHOST_MODE dest=$OFFHOST_DEST" | tee -a "$LOG"

case "$OFFHOST_MODE" in
  rsync)
    rsync -av --checksum \
      "$SRC_ROOT/ia-bot-trading/" \
      "$OFFHOST_DEST/ia-bot-trading/"
    # Consultate opcional si existe
    if [[ -d "$SRC_ROOT/consultate" ]]; then
      rsync -av --checksum \
        "$SRC_ROOT/consultate/" \
        "$OFFHOST_DEST/consultate/"
    fi
    ;;
  *)
    echo "ERROR: OFFHOST_MODE no soportado: $OFFHOST_MODE" >&2
    exit 3
    ;;
esac

echo "[$TS] sync OK" | tee -a "$LOG"
