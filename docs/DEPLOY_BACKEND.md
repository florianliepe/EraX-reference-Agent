# Backend deployment runbook

This runbook deploys the FastAPI image to Azure Container Apps, stores the pilot password as a Container Apps secret, sets the public backend URL as the GitHub repository variable `VITE_API_URL`, and rebuilds the GitHub Pages frontend.

It creates billable Azure resources. Run it only in an approved subscription and resource group. The application currently stores jobs and files on the container filesystem, so keep one replica and treat redeployments/restarts as destructive to in-flight and completed jobs.

## Prerequisites

- Azure CLI (`az`) with permission to create resources and role assignments in the target subscription.
- GitHub CLI (`gh`) authenticated for `florianliepe/EraX-reference-Agent` with repository and workflow access.
- A globally unique, lowercase Azure Container Registry name.
- An approved pilot password. Do not store it in a GitHub variable or any `VITE_*` setting.

## Deploy

Run the following in PowerShell from the repository root. Replace the three values marked `REPLACE_ME`.

```powershell
$SubscriptionId = 'REPLACE_ME'
$ResourceGroup = 'REPLACE_ME'
$RegistryName = 'REPLACE_ME'
$Location = 'westeurope'
$EnvironmentName = 'erax-reference-env'
$AppName = 'erax-reference-api'
$ImageTag = (git rev-parse --short HEAD)
$PilotPassword = Read-Host 'Pilot password' -AsSecureString
$PilotPasswordPlain = [System.Net.NetworkCredential]::new('', $PilotPassword).Password

az login
az account set --subscription $SubscriptionId
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

az group create --name $ResourceGroup --location $Location
az acr create --name $RegistryName --resource-group $ResourceGroup --sku Basic --admin-enabled true
az acr build --registry $RegistryName --image "erax-reference-api:$ImageTag" --file infra/backend.Dockerfile .
az containerapp env create --name $EnvironmentName --resource-group $ResourceGroup --location $Location

$RegistryUser = az acr credential show --name $RegistryName --query username -o tsv
$RegistryPassword = az acr credential show --name $RegistryName --query 'passwords[0].value' -o tsv
$Image = "$RegistryName.azurecr.io/erax-reference-api:$ImageTag"

az containerapp create `
  --name $AppName `
  --resource-group $ResourceGroup `
  --environment $EnvironmentName `
  --image $Image `
  --registry-server "$RegistryName.azurecr.io" `
  --registry-username $RegistryUser `
  --registry-password $RegistryPassword `
  --ingress external `
  --target-port 8000 `
  --min-replicas 1 `
  --max-replicas 1 `
  --secrets "pilot-password=$PilotPasswordPlain" `
  --env-vars 'PILOT_PASSWORD=secretref:pilot-password' 'CORS_ORIGINS=https://florianliepe.github.io' 'DATA_DIR=/app/data'

$Fqdn = az containerapp show --name $AppName --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
$BackendUrl = "https://$Fqdn"
Invoke-RestMethod "$BackendUrl/health"

gh variable set VITE_API_URL --repo florianliepe/EraX-reference-Agent --body $BackendUrl
gh workflow run ci.yml --repo florianliepe/EraX-reference-Agent --ref main

$PilotPasswordPlain = $null
$RegistryPassword = $null
Write-Host "Backend: $BackendUrl"
Write-Host 'Frontend: https://florianliepe.github.io/EraX-reference-Agent/'
```

The health request must return `{"status":"ok"}` before setting `VITE_API_URL`. After the workflow completes, open the frontend and perform one upload-to-download smoke test.

## Verify and inspect

```powershell
gh variable get VITE_API_URL --repo florianliepe/EraX-reference-Agent
gh run list --repo florianliepe/EraX-reference-Agent --workflow ci.yml --limit 3
az containerapp logs show --name $AppName --resource-group $ResourceGroup --follow
```

## Update an existing deployment

Build a new image and point the existing app at it:

```powershell
$ImageTag = (git rev-parse --short HEAD)
az acr build --registry $RegistryName --image "erax-reference-api:$ImageTag" --file infra/backend.Dockerfile .
az containerapp update --name $AppName --resource-group $ResourceGroup --image "$RegistryName.azurecr.io/erax-reference-api:$ImageTag"
```

For production, replace ACR admin credentials with managed identity, place secrets in Azure Key Vault, add durable object/database storage, and replace the shared pilot password with Entra ID authentication.
