#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

sudo apt update
sudo apt install -y htop tmux curl ca-certificates python3 python3-pip python3-venv psmisc

echo "Deps installed."
