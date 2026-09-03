#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="$HOME/Applications/ADILocalAI.app"
ACTION="${1:-status}"

case "$ACTION" in
    install)
        mkdir -p "$HOME/Applications" "$SCRIPT_DIR/data/logs" "$SCRIPT_DIR/data/state"
        osacompile -o "$APP_PATH" -e "do shell script \"$SCRIPT_DIR/scripts/daemon.sh > /dev/null 2>&1 &\""
        osascript -e "tell application \"System Events\" to delete (every login item whose name is \"ADILocalAI\")" 2>/dev/null || true
        osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP_PATH\", hidden:true, name:\"ADILocalAI\"}"
        echo "✅ ADI Local AI berhasil didaftarkan ke macOS Login Items ($APP_PATH)."
        echo "Sistem akan otomatis berjalan setiap PC Anda menyala / login."
        ;;

    uninstall)
        osascript -e "tell application \"System Events\" to delete (every login item whose name is \"ADILocalAI\")" 2>/dev/null || true
        rm -rf "$APP_PATH"
        echo "Auto-start Login Item dihapus."
        ;;

    start)
        if curl -s http://127.0.0.1:8741/status >/dev/null 2>&1; then
            curl -s -X POST http://127.0.0.1:8741/start
            echo "Permintaan start dikirim ke supervisor."
        else
            echo "Memulai supervisor daemon..."
            nohup "$SCRIPT_DIR/scripts/daemon.sh" > "$SCRIPT_DIR/data/logs/daemon.log" 2>&1 &
            sleep 2
            curl -s -X POST http://127.0.0.1:8741/start 2>/dev/null || true
            echo "Supervisor & AI Engine dimulai."
        fi
        ;;

    stop)
        if curl -s http://127.0.0.1:8741/status >/dev/null 2>&1; then
            curl -s -X POST http://127.0.0.1:8741/stop
            echo ""
        fi
        pkill -f "local_ai.api:app" 2>/dev/null || true
        echo "AI Engine dihentikan."
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        echo "=== ADI Local AI Status ==="
        LOGIN_ITEM=$(osascript -e 'tell application "System Events" to get name of every login item' 2>/dev/null || echo "")
        if [[ "$LOGIN_ITEM" == *"ADILocalAI"* ]]; then
            echo "Auto-Start on Boot (macOS Login Item): AKTIF (ADILocalAI.app)"
        else
            echo "Auto-Start on Boot (macOS Login Item): TIDAK AKTIF"
        fi

        SUP_RES=$(curl -s http://127.0.0.1:8741/status 2>/dev/null || echo "offline")
        if [[ "$SUP_RES" != "offline" ]]; then
            echo "Supervisor Daemon (Port 8741): ONLINE"
        else
            echo "Supervisor Daemon (Port 8741): OFFLINE"
        fi

        AI_RES=$(curl -s http://127.0.0.1:8742/health 2>/dev/null || echo "offline")
        if [[ "$AI_RES" != "offline" ]]; then
            echo "AI Engine (Port 8742): ONLINE & RUNNING"
        else
            echo "AI Engine (Port 8742): OFFLINE / STOPPED"
        fi
        ;;

    *)
        echo "Usage: $0 {install|uninstall|start|stop|restart|status}"
        exit 1
        ;;
esac
