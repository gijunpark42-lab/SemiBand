#!/usr/bin/env bash
# One-shot setup on a fresh Ubuntu 22.04/24.04 VM (GCP e2-micro / Oracle Always Free).
# Run as the login user (not root):   bash setup.sh
#
# Installs python + deps into /opt/semiband/venv, clones the repo, adds 1G swap
# (the free VMs have ~1GB RAM), and installs systemd units for the three bots
# plus a weekly fundamentals refresh. The .env is NOT created here: copy it up
# with   scp .env <user>@<vm-ip>:/opt/semiband/.env   before starting.
set -euo pipefail

REPO="https://github.com/gijunpark42-lab/SemiBand.git"
DIR=/opt/semiband
USER_NAME=$(whoami)

sudo apt-get update -y
sudo apt-get install -y git python3 python3-venv python3-pip

# swap: pandas + 3 bots on 1GB RAM is tight without it
if ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

if [ ! -d "$DIR/.git" ]; then
  sudo mkdir -p "$DIR" && sudo chown "$USER_NAME" "$DIR"
  git clone "$REPO" "$DIR"
fi
cd "$DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# systemd units (templated with the login user)
for unit in deploy/systemd/*.service deploy/systemd/*.timer; do
  sed "s|__USER__|$USER_NAME|g" "$unit" | sudo tee "/etc/systemd/system/$(basename "$unit")" > /dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable semiband-stocks semiband-feed semiband-crypto semiband-earnings semiband-scalp semiband-fundamentals.timer

echo
echo "Setup done. Next:"
echo "  1. scp your .env to $DIR/.env   (chmod 600)"
echo "  2. sudo systemctl start semiband-stocks semiband-feed semiband-crypto semiband-earnings semiband-scalp semiband-fundamentals.timer"
echo "  3. journalctl -fu semiband-crypto     (live log)"
