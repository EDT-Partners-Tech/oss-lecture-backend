# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

#!/bin/bash

UUID=$1
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMP_DIR="$BASE_DIR/temp"
INPUT_FILE="$TEMP_DIR/${UUID}.pdf"
OUTPUT_FILE="${UUID}.html"
LOG_FILE="${TEMP_DIR}/${UUID}_debug.log"

echo "=== PDF to HTML DEBUG ==="
echo "UUID: $UUID"
echo "BASE_DIR: $BASE_DIR"
echo "TEMP_DIR: $TEMP_DIR"
echo "INPUT_FILE: $INPUT_FILE"
echo "OUTPUT_FILE: $OUTPUT_FILE"
echo ""

# Buscar ruta absoluta de pdf2htmlEX
PDF2HTMLEX_PATH=$(command -v pdf2htmlEX)
if [[ -z "$PDF2HTMLEX_PATH" ]]; then
  echo "❌ No se encontró pdf2htmlEX en el PATH."
  exit 1
fi
echo "📍 pdf2htmlEX encontrado en: $PDF2HTMLEX_PATH"
echo ""

# Verificar que exista el archivo PDF
if [[ ! -f "$INPUT_FILE" ]]; then
  echo "❌ PDF no encontrado: $INPUT_FILE"
  exit 1
fi

cd "$TEMP_DIR" || {
  echo "❌ No se pudo acceder al directorio: $TEMP_DIR"
  exit 1
}

echo "🛠️ Ejecutando pdf2htmlEX..." | tee "$LOG_FILE"

# Ejecutar en entorno limpio
env -i "$PDF2HTMLEX_PATH" \
  --embed-css 1 \
  --embed-font 1 \
  --embed-image 1 \
  --embed-javascript 1 \
  --embed-outline 0 \
  --split-pages 0 \
  --dest-dir . \
  "${UUID}.pdf" \
  "${OUTPUT_FILE}" >> "$LOG_FILE" 2>&1

# Verificar y mostrar resultado
echo ""
HTML_SIZE=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || echo 0)
echo "📦 HTML size: $HTML_SIZE bytes"
echo "--- HTML preview ---"
head -n 20 "$OUTPUT_FILE" || echo "(archivo vacío)"
echo "--- End preview ---"

echo "📄 Archivos generados:"
ls -lh "${TEMP_DIR}/${UUID}"*

if [[ "$HTML_SIZE" -eq 0 ]]; then
  echo "❌ HTML vacío o conversión fallida."
  exit 2
else
  echo "✅ Conversión exitosa: $OUTPUT_FILE"
  exit 0
fi
