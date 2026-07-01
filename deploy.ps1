Write-Host "Pushing to GitHub..."
git push

Write-Host "Deploying to server..."
ssh -i "$HOME\.ssh\id_ed25519_lexicro" root@178.105.92.172 "/opt/lexicro/deploy.sh"

Write-Host "Done."