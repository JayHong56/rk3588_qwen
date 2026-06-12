#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/home/linaro/Qwen/tts}"

TTS_DIR="$BASE/02_rk3588_melotts_rknn2_deploy_project"
BRIDGE_DIR="$BASE/03_rk3588_qwen35_melotts_voice_bridge_project"

LOG_DIR="$BASE/logs"
RUN_DIR="$BASE/run"

TTS_LOG="$LOG_DIR/melotts_tts.log"
BRIDGE_LOG="$LOG_DIR/qwen_melotts_bridge.log"

TTS_PID="$RUN_DIR/melotts_tts.pid"
BRIDGE_PID="$RUN_DIR/qwen_melotts_bridge.pid"

mkdir -p "$LOG_DIR" "$RUN_DIR"

load_env() {
    local env_file="$1"
    if [ -f "$env_file" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$env_file"
        set +a
    fi
}

is_alive() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file" 2>/dev/null || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

wait_http() {
    local url="$1"
    local name="$2"
    local retry="${3:-60}"

    echo "[INFO] waiting for $name: $url"

    for i in $(seq 1 "$retry"); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            echo "[OK] $name ready"
            return 0
        fi
        sleep 1
    done

    echo "[ERR] $name not ready: $url"
    return 1
}

check_dirs() {
    if [ ! -d "$TTS_DIR" ]; then
        echo "[ERR] TTS_DIR not found: $TTS_DIR"
        exit 1
    fi

    if [ ! -d "$BRIDGE_DIR" ]; then
        echo "[ERR] BRIDGE_DIR not found: $BRIDGE_DIR"
        exit 1
    fi

    if [ ! -f "$TTS_DIR/.venv/bin/activate" ]; then
        echo "[ERR] TTS venv not found: $TTS_DIR/.venv"
        echo "      Please run TTS env setup first."
        exit 1
    fi

    if [ ! -f "$BRIDGE_DIR/.venv/bin/activate" ]; then
        echo "[ERR] Bridge venv not found: $BRIDGE_DIR/.venv"
        echo "      Please run bridge env setup first."
        exit 1
    fi
}

check_qwen_cmd() {
    load_env "$BRIDGE_DIR/config/voice_bridge.env"

    if [ "${QWEN_BACKEND:-openai}" = "cmd" ]; then
        if [ -z "${QWEN_CMD:-}" ]; then
            echo "[ERR] QWEN_BACKEND=cmd but QWEN_CMD is empty"
            exit 1
        fi

        if [ ! -x "$QWEN_CMD" ]; then
            echo "[ERR] QWEN_CMD not executable: $QWEN_CMD"
            echo "      Try: chmod +x $QWEN_CMD"
            exit 1
        fi

        echo "[OK] Qwen cmd backend: $QWEN_CMD"
    else
        echo "[INFO] Qwen backend: ${QWEN_BACKEND:-openai}"
        echo "[INFO] Qwen API base: ${QWEN_API_BASE:-http://127.0.0.1:8000/v1}"
    fi
}

start_tts() {
    check_dirs

    load_env "$TTS_DIR/config/melotts.env"
    local port="${MELOTTS_PORT:-8010}"

    if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        echo "[OK] MeloTTS service already running on port $port"
        return 0
    fi

    if is_alive "$TTS_PID"; then
        echo "[WARN] old TTS pid exists but health check failed. pid=$(cat "$TTS_PID")"
    fi

    echo "[INFO] starting MeloTTS-RKNN2 service..."
    echo "[INFO] log: $TTS_LOG"

    (
        cd "$TTS_DIR"
        exec bash scripts/05_start_api.sh
    ) >"$TTS_LOG" 2>&1 &

    echo $! > "$TTS_PID"

    if ! wait_http "http://127.0.0.1:$port/health" "MeloTTS-RKNN2" 90; then
        echo "[ERR] MeloTTS-RKNN2 start failed. Last logs:"
        tail -n 80 "$TTS_LOG" || true
        exit 1
    fi
}

start_bridge() {
    check_dirs
    check_qwen_cmd

    load_env "$BRIDGE_DIR/config/voice_bridge.env"
    local port="${BRIDGE_PORT:-8020}"

    if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        echo "[OK] Bridge service already running on port $port"
        return 0
    fi

    echo "[INFO] starting Qwen + MeloTTS bridge service..."
    echo "[INFO] log: $BRIDGE_LOG"

    (
        cd "$BRIDGE_DIR"
        exec bash scripts/04_start_bridge_api.sh
    ) >"$BRIDGE_LOG" 2>&1 &

    echo $! > "$BRIDGE_PID"

    if ! wait_http "http://127.0.0.1:$port/health" "Qwen-MeloTTS Bridge" 40; then
        echo "[ERR] Bridge start failed. Last logs:"
        tail -n 80 "$BRIDGE_LOG" || true
        exit 1
    fi
}

stop_one() {
    local name="$1"
    local pid_file="$2"

    if is_alive "$pid_file"; then
        local pid
        pid="$(cat "$pid_file")"
        echo "[INFO] stopping $name pid=$pid"
        kill "$pid" 2>/dev/null || true

        for _ in $(seq 1 10); do
            if kill -0 "$pid" 2>/dev/null; then
                sleep 1
            else
                break
            fi
        done

        if kill -0 "$pid" 2>/dev/null; then
            echo "[WARN] force killing $name pid=$pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
    else
        echo "[INFO] $name not running by pid file"
    fi

    rm -f "$pid_file"
}

start_all() {
    start_tts
    start_bridge
    echo
    echo "[OK] voice stack started"
    echo "     TTS API    : http://127.0.0.1:${MELOTTS_PORT:-8010}"
    echo "     Bridge API : http://127.0.0.1:${BRIDGE_PORT:-8020}"
}

stop_all() {
    stop_one "Qwen-MeloTTS Bridge" "$BRIDGE_PID"
    stop_one "MeloTTS-RKNN2" "$TTS_PID"
    echo "[OK] voice stack stopped"
}

status_all() {
    echo "========== PID =========="
    if is_alive "$TTS_PID"; then
        echo "MeloTTS-RKNN2       running pid=$(cat "$TTS_PID")"
    else
        echo "MeloTTS-RKNN2       not running by pid file"
    fi

    if is_alive "$BRIDGE_PID"; then
        echo "Qwen-MeloTTS Bridge running pid=$(cat "$BRIDGE_PID")"
    else
        echo "Qwen-MeloTTS Bridge not running by pid file"
    fi

    echo
    echo "========== HTTP =========="
    load_env "$TTS_DIR/config/melotts.env"
    local tts_port="${MELOTTS_PORT:-8010}"

    load_env "$BRIDGE_DIR/config/voice_bridge.env"
    local bridge_port="${BRIDGE_PORT:-8020}"

    echo -n "TTS health    : "
    curl -fsS "http://127.0.0.1:$tts_port/health" 2>/dev/null || echo "DOWN"

    echo
    echo -n "Bridge health : "
    curl -fsS "http://127.0.0.1:$bridge_port/health" 2>/dev/null || echo "DOWN"
    echo
}

test_tts() {
    start_tts

    echo "[INFO] testing TTS..."
    (
        cd "$BRIDGE_DIR"
        source .venv/bin/activate
        bash scripts/02_check_tts_api.sh
    )
}

test_qwen() {
    check_dirs
    check_qwen_cmd

    echo "[INFO] testing Qwen backend..."
    (
        cd "$BRIDGE_DIR"
        source .venv/bin/activate
        bash scripts/01_check_qwen_api.sh
    )
}

chat_once() {
    start_tts

    local prompt="${*:-请描述这张图片。}"

    echo "[INFO] running voice chat..."
    echo "[PROMPT] $prompt"

    (
        cd "$BRIDGE_DIR"
        source .venv/bin/activate
        bash scripts/03_run_voice_chat.sh "$prompt"
    )
}

chat_parallel() {
    start_tts

    local prompt="${*:-<image>请用三句话描述这张图片，每句话不超过20个字。}"

    echo "[INFO] running parallel voice chat..."
    echo "[PROMPT] $prompt"

    (
        cd "$BASE"
        PYTHONUNBUFFERED=1 \
        QWEN_CMD=/home/linaro/Qwen/run_qwen3vl_stream.sh \
        TTS_URL=http://127.0.0.1:8010/speak \
        python3 /home/linaro/Qwen/tts/stream_qwen_tts_parallel.py "$prompt"
    )
}

api_chat() {
    start_all

    local prompt="${*:-请描述这张图片。}"

    load_env "$BRIDGE_DIR/config/voice_bridge.env"
    local bridge_port="${BRIDGE_PORT:-8020}"

    curl -X POST "http://127.0.0.1:$bridge_port/chat_speak" \
        -H "Content-Type: application/json" \
        -d "{\"prompt\":\"$prompt\",\"speak\":true}"
    echo
}

show_logs() {
    echo "========== MeloTTS log =========="
    tail -n 80 "$TTS_LOG" 2>/dev/null || echo "No TTS log"

    echo
    echo "========== Bridge log =========="
    tail -n 80 "$BRIDGE_LOG" 2>/dev/null || echo "No bridge log"
}

case "${1:-help}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 1
        start_all
        ;;
    status)
        status_all
        ;;
    test-tts)
        test_tts
        ;;
    test-qwen)
        test_qwen
        ;;
    chat)
        shift
        chat_once "$@"
        ;;
    chat-parallel)
        shift
        chat_parallel "$@"
        ;;
    api-chat)
        shift
        api_chat "$@"
        ;;
    logs)
        show_logs
        ;;
    help|*)
        cat <<USAGE
Usage:
  $0 start                         启动 TTS 服务 + 桥接 API 服务
  $0 stop                          停止服务
  $0 restart                       重启服务
  $0 status                        查看服务状态
  $0 logs                          查看最近日志

  $0 test-tts                      测试 MeloTTS-RKNN2 播报
  $0 test-qwen                     测试 Qwen 后端，cmd/openai 都支持

  $0 chat "请描述这张图片。"        直接跑一次语音对话，不依赖 bridge API
  $0 chat-parallel "请描述这张图片。" 边生成边按句播报，Qwen 和 TTS 并行
  $0 api-chat "请描述这张图片。"    通过 bridge API 跑一次语音对话

Current paths:
  BASE       = $BASE
  TTS_DIR    = $TTS_DIR
  BRIDGE_DIR = $BRIDGE_DIR

USAGE
        ;;
esac
