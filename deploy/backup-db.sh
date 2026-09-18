#!/usr/bin/env bash
# Copia diaria de la base de Black Volt, en formato personalizado, con retención.
#
# Instalar en el VPS por cron (ver deploy/vps-deploy.md):
#   crontab -e →  30 4 * * *  /home/enderj/Black-Volt-Mobility/deploy/backup-db.sh >> /home/enderj/blackvolt-backup.log 2>&1
#
# ## Qué cambió, y por qué no era una manía
#
# La versión anterior hacía `docker exec ... pg_dump > "$OUT"` directamente
# sobre el nombre definitivo. El `>` del shell crea el fichero ANTES de que
# pg_dump diga una palabra, así que un volcado que muere a la mitad —el
# contenedor reiniciándose, el disco lleno, la base rechazando la conexión—
# deja un `.dump` truncado, o de cero bytes, con la fecha de hoy y el nombre
# de una copia buena. `set -e` aborta el guion, sí, pero el fichero se queda.
# A la noche siguiente la retención lo cuenta como una de las catorce, y el
# Mac se lo lleva como la más nueva. Catorce fallos seguidos y no queda ni una
# copia válida, sin un solo error a la vista.
#
# Aquí un volcado solo se llama copia cuando se ha demostrado que se puede leer:
#
#   1. se vuelca DENTRO del contenedor, sobre un fichero de verdad;
#   2. se le pide a `pg_restore` el índice — si no se puede leer, no es
#      restaurable, y punto;
#   3. se comprueba que ese índice trae las tablas sin las cuales esto no sirve
#      de nada, porque un volcado de una base vacía supera el paso 2 tan
#      contento;
#   4. se saca a un `.part` que un `trap` borra si algo falla, y solo entonces
#      se le pone el nombre definitivo.
#
# La retención mira únicamente ficheros ya verificados: un fallo no puede echar
# fuera a una copia buena.
#
# ## Dos trampas medidas en el guion gemelo de Zorros
#
# - **`docker exec` se bebe la entrada estándar.** Cuando este guion se llama
#   desde otro que llega por una tubería (`ssh vps 'bash -s' < guion.sh`, que es
#   como se despliega), lo que se bebe es el RESTO DEL GUION QUE LO LLAMÓ. Por
#   eso cada `docker exec` lleva `< /dev/null`.
# - **`printf ... | grep -q` bajo `pipefail` MIENTE.** `grep -q` sale en cuanto
#   encuentra la coincidencia y cierra la tubería; `printf`, que aún tiene
#   decenas de KB por escribir, muere con SIGPIPE, y `pipefail` devuelve ESE
#   fallo aunque grep sí había encontrado la tabla. Rechazaba 1 de cada 20
#   copias buenas, y siempre las tablas que salen antes en el índice. Aquí se
#   comprueba con `case`: sin subproceso, sin tubería, sin azar.
#
# ## Esto NO es una copia de seguridad todavía
#
# Vive en el mismo disco que la base. Si la máquina muere, se van las dos. La
# copia de verdad la tira el Mac con el agente `com.vps.pullall` del repo de
# Zorros, y va en esa dirección a propósito: el VPS no guarda ninguna credencial
# hacia el almacén, así que quien entre aquí no puede borrar también las copias.
set -euo pipefail

CONTAINER="${BV_DB_CONTAINER:-blackvolt-db}"
DB_USER="${POSTGRES_USER:-blackvolt}"
DB_NAME="${POSTGRES_DB:-blackvolt}"
OUT_DIR="${BV_BACKUP_DIR:-$HOME/blackvolt-backups}"
KEEP="${BV_BACKUP_KEEP:-14}"
# Las tablas sin las cuales un volcado de Black Volt no sirve para nada: los
# viajes, el dinero, los clientes y los inquilinos. Si el índice no las nombra,
# el volcado es de otra base o de una vacía.
MUST_HAVE="${BV_BACKUP_TABLES:-rides payments clients tenants}"

say() { echo "$(date -Is) $*"; }

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
# El temporal lleva PID además de la marca. La marca tiene resolución de
# SEGUNDO, así que dos corridas dentro del mismo segundo —el cron y una a mano,
# o un reintento— compartirían fichero y se pisarían. El nombre DEFINITIVO
# sigue siendo por segundo: dos copias del mismo segundo son la misma copia.
UNIQ="$STAMP-$$"
TMP="$OUT_DIR/.blackvolt-$UNIQ.part"
OUT="$OUT_DIR/blackvolt-$STAMP.dump"
IN_BOX="/tmp/blackvolt-backup-$UNIQ.dump"

limpiar() {
  rm -f "$TMP"
  docker exec "$CONTAINER" rm -f "$IN_BOX" < /dev/null > /dev/null 2>&1 || true
}
trap limpiar EXIT

# El volcado se hace dentro del contenedor, sobre un fichero de verdad, y se
# verifica ahí mismo antes de salir. `pg_restore` lee un fichero con posición,
# no un flujo: verificar sobre una tubería da falsos negativos que no se
# reproducen, y un verificador de copias que se equivoca a veces es peor que
# ninguno.
docker exec "$CONTAINER" sh -c "pg_dump -U $DB_USER -Fc $DB_NAME > $IN_BOX" < /dev/null

# (1) ¿se puede leer el índice?
TOC="$(docker exec "$CONTAINER" pg_restore --list "$IN_BOX" < /dev/null)"

# (2) ¿trae lo que tiene que traer?
for tbl in $MUST_HAVE; do
  case "$TOC" in
    *"TABLE DATA public $tbl "*) ;;
    *)
      say "ABORTADO: el volcado no contiene la tabla '$tbl' — no se promueve"
      exit 1
      ;;
  esac
done

docker cp "$CONTAINER:$IN_BOX" "$TMP" > /dev/null
SIZE="$(wc -c < "$TMP" | tr -d ' ')"
# Un volcado de Black Volt pesa cientos de KB. Si sale de tres cifras, algo se
# cortó entre el contenedor y el disco y no vale como copia. El suelo es
# deliberadamente bajo para que una base que encoge de verdad (una purga, un
# inquilino que se va) no lo dispare: esto atrapa «el contenedor arrancó sobre
# un volumen vacío», no vigila el tamaño.
if [ "$SIZE" -lt 1024 ]; then
  say "ABORTADO: el fichero que salió del contenedor pesa $SIZE bytes — no se promueve"
  exit 1
fi

mv "$TMP" "$OUT"
# `grep -c` lee toda la entrada, así que aquí no hay SIGPIPE que valga; aun así
# el `|| true` evita que un recuento de cero tumbe el guion DESPUÉS de haber
# promovido una copia buena.
TABLAS="$(printf '%s\n' "$TOC" | grep -c 'TABLE DATA' || true)"
say "escrito $OUT ($(du -h "$OUT" | cut -f1)), $TABLAS tablas con datos"

# Retención: solo sobre ficheros ya verificados. Los `.part` no casan con este
# patrón, así que una racha de fallos no puede rotar fuera a la última copia
# buena.
ls -1t "$OUT_DIR"/blackvolt-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
say "retención: se guardan las $KEEP más nuevas ($(ls -1 "$OUT_DIR"/blackvolt-*.dump 2>/dev/null | wc -l | tr -d ' ') presentes)"
