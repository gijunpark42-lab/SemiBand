# Running the bots 24/7 on a free VM

Both free options below give ~1 GB RAM, which is enough for the three bots
(the setup script adds 1 GB swap).

| | Google Cloud e2-micro (recommended) | Oracle Always Free |
|---|---|---|
| Cost | $0 forever, 1 VM in us-west1 / us-central1 / us-east1 | $0 forever |
| Spec | 0.25 vCPU shared, 1 GB RAM, 30 GB standard disk | AMD micro x2 (1 GB) or Arm 2 OCPU / 12 GB |
| Catch | must stay in those 3 US regions, standard disk, standard network tier | signup can reject cards, Arm often "out of host capacity", idle VMs get reclaimed |

Pick **GCP us-east1** (closest to Alpaca, provisions in seconds).

## 1. Create the VM (Google Cloud)

1. console.cloud.google.com -> new project -> Compute Engine -> Create instance
2. Region **us-east1**, machine type **e2-micro**
3. Boot disk: **Ubuntu 24.04 LTS**, type **Standard persistent disk**, 30 GB
4. Networking -> Network service tier: **Standard**
5. Create. Note the external IP. Connect with the browser SSH button or
   `gcloud compute ssh <name>`.

## 2. Install

```bash
curl -fsSL https://raw.githubusercontent.com/gijunpark42-lab/SemiBand/main/deploy/setup.sh | bash
```

## 3. Copy the secrets and start

From your PC (PowerShell, in the Trading folder):

```powershell
scp .env <user>@<vm-ip>:/opt/semiband/.env
```

On the VM:

```bash
chmod 600 /opt/semiband/.env
sudo systemctl start semiband-stocks semiband-feed semiband-crypto semiband-earnings semiband-scalp semiband-fundamentals.timer
```

## Day to day

```bash
systemctl status semiband-*                 # what is running
journalctl -fu semiband-crypto              # live crypto log (feed / scalp / stocks / earnings likewise)
cd /opt/semiband && git pull && sudo systemctl restart semiband-stocks semiband-feed semiband-crypto semiband-earnings semiband-scalp
```

`DRY_RUN` is read from `config.py` / `crypto_config.py`, so flipping it is a
commit + `git pull` + restart, same as any code change.
