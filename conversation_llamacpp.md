# Conversation : Configuration et Recherche dans Llama.cpp Server

## Échange 1
**Utilisateur :** comment rechercher dans la console llamacpp server

**Assistant :** Pour rechercher des informations dans la console ou les logs de `llama-server`, la méthode dépend de ce que vous souhaitez trouver : les requêtes HTTP, le contenu des prompts ou l'historique de l'interface web.

### 1. Activer les logs détaillés et les invites (Prompts)
Par défaut, `llama-server` n'affiche pas l'intégralité des prompts textuels envoyés par les utilisateurs dans la console. Pour forcer l'affichage complet des données reçues et générées afin de pouvoir y faire une recherche, vous devez lancer le serveur avec l'option `--verbose` :
```bash
llama-server -m votre_modele.gguf --verbose
```

### 2. Rechercher en temps réel ou dans l'historique (Linux / macOS)
* **Filtrer en direct un mot-clé (ex: "slot" ou "error") :**
  ```bash
  llama-server -m votre_modele.gguf --verbose 2>&1 | grep "mot-clé"
  ```
* **Sauvegarder les logs dans un fichier pour les analyser plus tard :**
  ```bash
  llama-server -m votre_modele.gguf --verbose > serveur.log 2>&1
  ```
  Vous pourrez ensuite rechercher à l'intérieur du fichier avec `grep "mon_prompt" serveur.log`.

### 3. Rechercher dans l'historique de l'Interface Web intégrée
Si vous utilisez l'interface de chat native sur `http://localhost:8080`, l'historique est stocké dans le `localStorage` du navigateur. Depuis la console de développement (F12) :
```javascript
console.table(localStorage);
```

---

## Échange 2
**Utilisateur :** je veux savoir son pid, son chemin et comment le configurer pour utiliser un modèles

**Assistant :** 

### 1. Trouver le PID et le chemin d'accès
* **Trouver le PID (Process ID) :**
  ```bash
  pgrep -fl llama-server
  ```
* **Trouver le chemin de l'exécutable (à partir de son PID, ex: 12345) :**
  ```bash
  ls -l /proc/12345/exe
  ```
  *(Sur macOS : `ps -p 12345 -o comm=`)*

### 2. Configurer le serveur pour utiliser un modèle
* **Option A : Via la ligne de commande (Direct)**
  ```bash
  /chemin/vers/llama-server -m /chemin/vers/votre_modele.gguf -c 4096 --port 8080
  ```
* **Option B : Via un fichier de configuration JSON**
  Créer un fichier `config.json` et le charger avec `llama-server --config config.json`.

---

## Échange 3
**Utilisateur :** (Retour console)
```
grep -fl llama-server
93283 ./vendor/llama.cpp/llama-server --port 8080 --host 127.0.0.1 --model ./models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf --ctx-size 65536 -ngl 99 --jinja --flash-attn on -ctk q8_0 -ctv q8_0 --predict 4096 --repeat-penalty 1.1 --skip-chat-parsing
```

**Assistant :** Analyse de votre serveur en cours d'exécution :
* **PID :** `93283`
* **Chemin :** `./vendor/llama.cpp/llama-server`
* **Modèle :** `./models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`

Votre commande actuelle est déjà très optimisée pour votre architecture. Pour modifier cette configuration, il faut arrêter le processus (`kill 93283`) et relancer la commande avec vos modifications.

---

## Échange 4
**Utilisateur :** (Retour console indiquant que l'utilisateur est dans la racine `/` et confirmation du PID).

**Assistant :** Comme vous êtes à la racine `/` mais utilisez des chemins relatifs, nous devons localiser le Working Directory exact avec :
```bash
lsof -p 93283 | grep cwd
```
Proposition de création d'un script `start.sh` automatisé pour encapsuler les paramètres.

---

## Échange 5
**Utilisateur :**
```
mac@MacBook-Pro-M1 / % lsof -p 93283 | grep cwd
llama-ser 93283  mac  cwd    DIR               1,14       1344            88310716 /Users/mac/Documents/Code/ChannelAgent
```

**Assistant :** Le dossier racine est `/Users/mac/Documents/Code/ChannelAgent`. Proposition d'un script bash interactif pour lister et choisir dynamiquement le modèle GGUF dans le dossier `./models/`.

---

## Échange 6
**Utilisateur :** (Fournit le contenu initial complet du fichier d'infrastructure `start.sh` du projet `ChannelAgent`, qui intègre les modes Docker, Native, Admin API, Backups, Rekey, etc.) : "voici le code actuel . peux tu vérifier et faire les modifications ou ajouts nécessaires ?"

**Assistant :** Analyse du fichier d'infrastructure. Identification de deux opportunités :
1. **L'argument manquant `--skip-chat-parsing` :** Présent dans votre commande manuelle mais absent de la ligne 306 du bloc de démarrage en arrière-plan (`nohup`).
2. **Gestion anti-conflit de port :** Si le modèle change dans le `.env` mais que l'ancien processus tourne toujours sur le port 8080, le script s'y connectait aveuglément au lieu d'alerter.

---

## Échange 7 & 8
**Utilisateur :** "oui tout est défini", puis "je veux le start.sh complet" et signalement d'un bug d'affichage (du texte hors du bloc de code en raison de commentaires mal interprétés par l'interface).

**Assistant :** Correction complète du problème de formatage en épurant les commentaires parasites pour assurer un bloc de code unique sans coupure.

---

## Script `start.sh` Final et Unifié (Épuré de commentaires)

```bash
#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE}")" && pwd)"
cd "$REPO_DIR"

create_env_from_example() {
  (umask 077; cp .env.example .env)
}

warn_if_env_is_shared() {
  local mode
  mode="$(python3 -c "import os; print(format(os.stat('.env').st_mode & 0o777, 'o'))")"
  if [ $(( 8#$mode & 8#077 )) -ne 0 ]; then
    echo "!! .env is readable by other users (mode \${mode}) and holds secrets. Restrict it: chmod 600 .env" >&2
  fi
}

show_config() {
  if [ ! -f .env ]; then
    echo "No .env found — copying from .env.example." >&2
    create_env_from_example
  fi
  warn_if_env_is_shared
  python3 - <<'PYEOF'
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "app"))
try:
    import settings_rules
except ImportError as exc:
    print(f"The configuration could not be shown: the rules module could not be loaded ({exc}).", file=sys.stderr)
    sys.exit(1)
sys.exit(settings_rules.cli_show(".env", ".env.example"))
PYEOF
}

set_config() {
  local kv="\${1:-}"
  if [[ "\$kv" != *=* ]]; then
    echo "Usage: ./start.sh --set KEY=VALUE" >&2
    exit 1
  fi
  local key="\${kv%%=*}"
  local value="\${kv#*=}"
  if ! [[ "\$key" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
    echo "'\${key}' is not a valid variable name (UPPER_CASE letters, digits and underscores)." >&2
    exit 1
  fi
  if [ ! -f .env ]; then
    create_env_from_example
  fi
  warn_if_env_is_shared
  python3 - "\$key" "\$value" <<'PYEOF'
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "app"))
try:
    import settings_rules
except ImportError as exc:
    print(f"{sys.argv[1]} was NOT changed: the value rules could not be loaded ({exc}).", file=sys.stderr)
    sys.exit(1)
sys.exit(settings_rules.cli_set(".env", ".env.example", sys.argv[1], sys.argv[2]))
PYEOF
  echo "==> Set \${key} in .env."
  echo "==> Applies at the next start: a running application keeps its old value until you restart it (./start.sh --stop, then ./start.sh)."
}

pid_alive() {
  local state
  kill -0 "\$1" 2>/dev/null || return 1
  state="\$(ps -p "\$1" -o stat= 2>/dev/null | tr -d ' ')"
  [ -n "\$state" ] && [ "\${state:0:1}" != "Z" ]
}

pid_is() {
  local file="\$1" pattern="\$2" pid
  [ -f "\$file" ] || return 1
  pid="\$(cat "\$file" 2>/dev/null || true)"
  [[ "\$pid" =~ ^[0-9]+$ ]] || return 1
  pid_alive "\$pid" || return 1
  ps -p "\$pid" -o command= 2>/dev/null | grep -q -- "\$pattern"
}

http_code() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 3 "\$1" 2>/dev/null || true
}

load_env_if_present() {
  if [ -f .env ]; then
    set -a
    source .env
    set +a
  fi
}

docker_running_container() {
  command -v docker >/dev/null 2>&1 || return 1
  docker compose ps --status running -q channelagent 2>/dev/null | head -n 1 | grep .
}

show_status() {
  load_env_if_present
  local llama_port="\${LLAMA_PORT:-8080}" api_port="\${API_SERVER_PORT:-8700}" code container
  echo "==> ChannelAgent status"

  if ! command -v docker >/dev/null 2>&1; then
    echo "  app (container)  : docker not available"
  elif container="\$(docker_running_container)"; then
    echo "  app (container)  : running (\${container:0:12})"
  else
    echo "  app (container)  : not running"
  fi

  if pid_is .app.pid "app.main"; then
    echo "  app (native)     : running (pid \$(cat .app.pid))"
  else
    echo "  app (native)     : not running"
  fi

  if [ -z "\${API_SERVER_KEY:-}" ]; then
    echo "  Admin API        : disabled (API_SERVER_KEY is not set)"
  else
    code="\$(http_code "http://127.0.0.1:\${api_port}/users")"
    case "\$code" in
      200|401|429) echo "  Admin API        : up on 127.0.0.1:\${api_port} (HTTP \${code})" ;;
      *) echo "  Admin API        : down on 127.0.0.1:\${api_port}" ;;
    esac
  fi

  code="\$(http_code "http://localhost:\${llama_port}/health")"
  if [ "$code" = "200" ]; then
    if pid_is .llama-server.pid "llama-server"; then
      echo "  llama-server     : up on port \${llama_port} (pid \$(cat .llama-server.pid), started by start.sh)"
    else
      echo "  llama-server     : up on port \${llama_port} (not started by start.sh)"
    fi
  else
    echo "  llama-server     : down on port \${llama_port}"
  fi
}

stop_pid_file() {
  local label="\$1" file="\$2" pattern="\$3" pid waited=0
  if pid_is "\$file" "\$pattern"; then
    pid="\$(cat "\$file")"
    kill "\$pid"
    while pid_alive "\$pid" && [ "\$waited" -lt 30 ]; do
      sleep 0.5
      waited=\$((waited + 1))
    done
    if pid_alive "\$pid"; then
      echo "!! \${label} (pid \${pid}) did not stop within 15 s; it was sent SIGTERM only." >&2
      return 1
    fi
    rm -f "\$file"
    echo "==> \${label} stopped (pid \${pid})."
  elif [ -f "\$file" ]; then
    pid="\$(cat "\$file" 2>/dev/null || true)"
    if [[ "\$pid" =~ ^[0-9]+$ ]] && pid_alive "\$pid"; then
      echo "!! \${file} names pid \${pid}, which is not \${label} (its command line does not match): left alone." >&2
    else
      rm -f "\$file"
      echo "==> \${label}: stale \${file} removed (no such process)."
    fi
  else
    echo "==> \${label}: not started by start.sh, nothing to stop."
  fi
}

stop_things() {
  local also_llama=0 status=0
  case "\${1:-}" in
    "") ;;
    --all) also_llama=1 ;;
    *) echo "Usage: ./start.sh --stop [--all]" >&2; exit 1 ;;
  esac
  load_env_if_present

  stop_pid_file "native app" .app.pid "app.main" || status=1

  if command -v docker >/dev/null 2>&1 && docker_running_container >/dev/null; then
    echo "==> Stopping the container (docker compose stop channelagent)."
    docker compose stop channelagent || status=1
  else
    echo "==> app (container): not running."
  fi

  if [ "\$also_llama" = "1" ]; then
    stop_pid_file "llama-server" .llama-server.pid "llama-server" || status=1
  else
    echo "==> llama-server left as it is (./start.sh --stop --all also stops the one this script started)."
  fi
  return "\$status"
}

case "\${1:-}" in
  --show-config)
    show_config
    exit 0
    ;;
  --set)
    set_config "\${2:-}"
    exit 0
    ;;
  --status)
    show_status
    exit 0
    ;;
  --stop)
    stop_things "\${2:-}"
    exit \$?
    ;;
esac

MODE="docker"
case "\${1:-}" in
  --native) MODE="native" ;;
  --admin) MODE="admin" ;;
  --restore) MODE="restore" ;;
  --rekey) MODE="rekey" ;;
  --describe) MODE="describe" ;;
  --api) MODE="api" ;;
  --models) MODE="models" ;;
esac

echo "==> ChannelAgent start.sh (mode: \$MODE)"

if [ ! -f .env ]; then
  echo "!! No .env found. Copying .env.example — fill in real values before running the app." >&2
  create_env_from_example
fi
warn_if_env_is_shared

if ! grep -q "^ENCRYPTION_KEY=.\+" .env; then
  echo "!! ENCRYPTION_KEY is missing or empty in .env — the app will refuse to start without it." >&2
  echo "!! Generate one with: python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"" >&2
  exit 1
fi

set -a
source .env
set +a

setup_venv() {
  if [ ! -d .venv ]; then
    echo "==> Creating virtualenv (.venv)"
    python3 -m venv .venv
  fi
  source .venv/bin/activate
  echo "==> Installing dependencies"
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
}

if [ "\$MODE" = "admin" ]; then
  setup_venv
  exec python3 -m app.admin.cli
fi

if [ "$MODE" = "rekey" ]; then
  setup_venv
  shift
  exec env -u ENCRYPTION_KEY -u OLD_ENCRYPTION_KEY python3 -m app.admin.rekey_guided "$@"
fi

if [ "\$MODE" = "describe" ]; then
  setup_venv
  shift
  exec python3 -m app.admin.client describe "$@"
fi

if [ "\$MODE" = "api" ]; then
  setup_venv
  shift
  export LLAMA_SERVER_URL="http://localhost:\${LLAMA_PORT:-8080}"
  exec python3 -m app.admin.client "$@"
fi

if [ "\$MODE" = "models" ]; then
  setup_venv
  shift
  export LLAMA_SERVER_URL="http://localhost:\${LLAMA_PORT:-8080}"
  models_sub="\${1:-}"
  [ "\$#" -gt 0 ] && shift
  case "\$models_sub" in
    list) exec python3 -m app.admin.client list-models "$@" ;;
    pull|import|delete)
      models_arg="\${1:-}"
      if [ -z "\$models_arg" ]; then
        echo "Usage: ./start.sh --models \${models_sub} <argument> [--name N.gguf] [--json]" >&2
        exit 1
      fi
      shift
      case "\$models_sub" in
        pull) exec python3 -m app.admin.client pull-model --spec "\$models_arg" "$@" ;;
        import) exec python3 -m app.admin.client import-model --path "\$models_arg" "$@" ;;
        delete) exec python3 -m app.admin.client delete-model --name "\$models_arg" "$@" ;;
      esac
      ;;
    *)
      echo "Usage: ./start.sh --models list | pull <repo[:quant]|url> | import <path> | delete <name>" >&2
      exit 1
      ;;
  esac
fi

if [ "\$MODE" = "restore" ]; then
  setup_venv
  shift
  exec python3 -m app.admin.restore "$@"
fi

LLAMA_PORT="\${LLAMA_PORT:-8080}"
if [ "\$(uname -s)" = "Darwin" ]; then
  router_mode="\${LLAMA_ROUTER_MODE:-false}"
  if [ "\$router_mode" = "true" ]; then
    model_args_ok=0
    [ -n "\${LLAMA_SERVER_BIN:-}" ] && [ -x "\${LLAMA_SERVER_BIN}" ]       && [ -d "\${MODELS_DIR:-}" ] && model_args_ok=1
    model_args=(--models-dir "\${MODELS_DIR:-}" --models-max "\${LLAMA_MODELS_MAX:-4}")
  else
    model_args_ok=0
    [ -n "\${LLAMA_SERVER_BIN:-}" ] && [ -x "\${LLAMA_SERVER_BIN}" ]       && [ -n "\${MODEL_FILE:-}" ] && [ -f "\${MODELS_DIR:-}/\${MODEL_FILE}" ] && model_args_ok=1
    model_args=(--model "\${MODELS_DIR:-}/\${MODEL_FILE:-}")
  fi
  
  if curl -sf --max-time 2 "http://localhost:\${LLAMA_PORT}/health" >/dev/null 2>&1; then
    if [ "\$router_mode" = "false" ] && ! pid_is .llama-server.pid "llama-server"; then
      echo "⚠️  Un serveur llama-server tourne déjà sur le port \${LLAMA_PORT} (hors start.sh)."
      echo "⚠️  Assurez-vous qu'il utilise bien le bon modèle (\${MODEL_FILE:-})."
    else
      echo "==> llama-server already running on localhost:\${LLAMA_PORT}."
    fi
  elif [ "\$model_args_ok" = "1" ]; then
    echo "==> llama-server not running — starting it (loading the model can take a while)."
    mkdir -p logs
    nohup env -i PATH="\$PATH" HOME="\$HOME" TMPDIR="\${TMPDIR:-/tmp}" LANG="\${LANG:-C}"       "\${LLAMA_SERVER_BIN}"       --port "\${LLAMA_PORT}"       --host 127.0.0.1       "\${model_args[@]}"       --ctx-size "\${LLAMA_CTX_SIZE:-65536}"       -ngl 99       --jinja       --flash-attn on       -ctk q8_0       -ctv q8_0       --predict 4096       --repeat-penalty 1.1       --skip-chat-parsing       > logs/llama-server.log 2>&1 &
    echo \$! > .llama-server.pid
    echo "==> Waiting for it to become healthy (pid \$(cat .llama-server.pid), log: logs/llama-server.log)..."
    ready=0
    for _ in \$(seq 1 150); do
      if curl -sf --max-time 2 "http://localhost:\${LLAMA_PORT}/health" >/dev/null 2>&1; then
        ready=1
        break
      fi
      sleep 2
    done
    if [ "\$ready" = "1" ]; then
      echo "==> llama-server is up. It keeps running after this script exits — stop it with:"
      echo "==>   kill \\$(cat .llama-server.pid)"
    else
      echo "!! llama-server did not become healthy in time — check logs/llama-server.log" >&2
      exit 1
    fi
  elif [ "\$router_mode" = "true" ]; then
    echo "!! llama-server is not reachable on localhost:\${LLAMA_PORT}, and LLAMA_SERVER_BIN /" >&2
    echo "!! MODELS_DIR are not both set to valid paths in .env, so router mode can't be" >&2
    echo "!! started automatically. Set those two (see .env.example), or start it yourself." >&2
    exit 1
  else
    echo "!! llama-server is not reachable on localhost:\${LLAMA_PORT}, and LLAMA_SERVER_BIN /" >&2
    echo "!! MODELS_DIR / MODEL_FILE are not all set to valid paths in .env, so it can't be" >&2
    echo "!! started automatically. Set those three (see .env.example), or start it yourself." >&2
    exit 1
  fi
fi

if [ "\$MODE" = "docker" ]; then
  mkdir -p data
  if [ "\$(uname -s)" = "Linux" ] && [ "\$(stat -c %u data 2>/dev/null || echo 10001)" != "10001" ]; then
    echo "!! data/ is not owned by uid 10001, the user the container runs as." >&2
    echo "!! Run once: sudo chown -R 10001:10001 data" >&2
  fi
  echo "==> Starting the container (docker compose up --build)."
  exec docker compose up --build
fi

setup_venv

export LLAMA_SERVER_URL="http://localhost:\${LLAMA_PORT}"
echo "==> Native mode: LLAMA_SERVER_URL overridden to \${LLAMA_SERVER_URL}"

echo "==> Starting app/main.py natively."
echo \$\$ > .app.pid
exec python3 -m app.main
```
