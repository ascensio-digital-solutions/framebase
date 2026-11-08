#!/usr/bin/env bash
# Builds the Web image from the current commit in Azure Container Registry (no local Docker needed) and
# points the staging Container App at that immutable digest. Run from anywhere in the repo:
#   Web/scripts/deploy-staging.sh
# Requires `az login` on the startup subscription. Refuses to deploy uncommitted Web/ changes.
set -euo pipefail

RG="rg-hair-sol-dev-cus"
ACR="crhairsoldevcus"
APP="framebase-web-staging"

cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain Web)" ]; then
  echo "Web/ has uncommitted changes. Commit them first so the deployed commit matches the image." >&2
  exit 1
fi

sha="$(git rev-parse --short HEAD)"
full="$(git rev-parse HEAD)"

echo "==> Building framebase-web:$sha in $ACR"
az acr build --registry "$ACR" --image "framebase-web:$sha" --build-arg "GIT_SHA=$full" \
  --file Web/Dockerfile Web --no-logs >/dev/null

digest="$(az acr repository show --name "$ACR" --image "framebase-web:$sha" --query digest -o tsv)"
image="$ACR.azurecr.io/framebase-web@$digest"

echo "==> Updating $APP to $image"
az containerapp update --name "$APP" --resource-group "$RG" --image "$image" --output none

fqdn="$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "==> Waiting for /healthz on https://$fqdn (cold start can take a minute)"
for i in $(seq 1 24); do
  body="$(curl -fsS -m 10 "https://$fqdn/healthz" 2>/dev/null || true)"
  case "$body" in *"$full"*) echo "Deployed $sha: $body"; exit 0 ;; esac
  sleep 5
done
echo "Deployed, but /healthz did not report commit $sha within 2 minutes. Check: az containerapp logs show -n $APP -g $RG" >&2
exit 1
