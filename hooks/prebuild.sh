#!/bin/bash

echo "=== Azure Prebuild Hook - Prisma Client Generation ==="

# Install Node.js dependencies
echo "Installing Node.js dependencies..."
npm install

# Generate Prisma client
echo "Generating Prisma client..."
npx prisma generate

# Verify generation
if [ -d "node_modules/.prisma/client" ]; then
    echo "✓ Prisma client generated successfully"
    ls -la node_modules/.prisma/client/
else
    echo "✗ Prisma client generation failed"
    exit 1
fi

echo "=== Prebuild completed successfully ==="
