#!/usr/bin/env bash
# Lance la simulation (serveur Python) puis la vue 3D Godot.
#
#   ./run3d.sh                      # avec le LLM (clé dans .env)
#   ./run3d.sh --offline            # sans LLM (gratuit)
#   ./run3d.sh --load               # reprendre la partie sauvegardée
#   ./run3d.sh --budget 1 --model openai/gpt-oss-20b
#   QUALITY=low ./run3d.sh          # qualité graphique : low / medium (défaut) / high
#
# Toutes les options sont transmises à « python main.py --serve ».
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
PORT="${PORT:-7777}"
QUALITY="${QUALITY:-}"          # vide = automatique

# --- Python
if [ ! -x .venv/bin/python ]; then
  echo "Création de l'environnement Python…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# --- Godot
GODOT="${GODOT:-}"
if [ -z "$GODOT" ]; then
  for c in godot godot4 "$HOME/.local/opt/godot/Godot_v4.7.2-stable_linux.x86_64"; do
    if command -v "$c" >/dev/null 2>&1 || { [ -f "$c" ] && [ -x "$c" ]; }; then GODOT="$c"; break; fi
  done
fi
if [ -z "$GODOT" ]; then
  echo "Godot 4 introuvable : téléchargez-le sur https://godotengine.org/download (4.7+)"
  echo "puis relancez avec GODOT=/chemin/vers/godot ./run3d.sh"
  exit 1
fi

# --- Assets (première fois)
if [ ! -f godot/assets/animations/UAL1.glb ]; then
  echo "Téléchargement des assets 3D (CC0, ~120 Mo)…"
  python3 tools/fetch_assets.py
fi
if [ ! -d godot/.godot/imported ] || [ ! -f godot/generated/ual_library.res ]; then
  echo "Import des assets dans Godot (une seule fois, ~1 min)…"
  (cd godot && "$GODOT" --headless --import >/dev/null 2>&1 || true)
  echo "Transfert des animations sur les personnages…"
  (cd godot && "$GODOT" --headless -s tools/bake_retarget.gd 2>&1 | grep -E "transf|ERROR" || true)
fi

# --- Simulation
.venv/bin/python main.py --serve --port "$PORT" "$@" &
SIM_PID=$!
# à la fermeture, la simulation sauvegarde la partie avant de quitter (SIGTERM géré par main.py)
trap 'kill -TERM $SIM_PID 2>/dev/null; wait $SIM_PID 2>/dev/null' EXIT INT TERM
sleep 1.5
if ! kill -0 $SIM_PID 2>/dev/null; then
  echo "La simulation n'a pas démarré."
  exit 1
fi

# --- Vue 3D
GARGS=(--port="$PORT")
[ -n "$QUALITY" ] && GARGS+=(--quality="$QUALITY")
# GODOT_ARGS : options supplémentaires pour la vue (ex. captures automatiques)
(cd godot && "$GODOT" -- "${GARGS[@]}" ${GODOT_ARGS:-}) || true
