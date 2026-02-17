#!/bin/bash
pnpm run build
sudo rm -rf /app-pages/miaobu
sudo cp -r dist /app-pages/miaobu
