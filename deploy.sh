#!/bin/bash
cd /opt/lexicro
git pull
docker-compose rm -f api
docker-compose up -d
echo "Deployed successfully"