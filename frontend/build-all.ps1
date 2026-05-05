$portals = @("patient", "doctor", "pharmacy", "reception", "admin", "demo", "main")

# Ensure dist folder exists
if (-not (Test-Path "dist")) {
    New-Item -ItemType Directory -Path "dist" | Out-Null
}

# Backup the original environment.ts
if (Test-Path "src\environments\environment.ts") {
    Copy-Item "src\environments\environment.ts" -Destination "src\environments\environment.backup.ts" -Force
}

foreach ($portal in $portals) {
    Write-Host "========================================="
    Write-Host "Building portal: $portal"
    Write-Host "========================================="
    
    # Swap the environment file manually to bypass Angular's fileReplacement quirks
    Copy-Item "src\environments\environment.$portal.ts" -Destination "src\environments\environment.ts" -Force
    
    # Clean up default output folder before building
    if (Test-Path "dist\pulse-q") {
        Remove-Item "dist\pulse-q" -Recurse -Force
    }
    
    # Run the build command WITHOUT the --configuration flag since we manually swapped the file
    npm run ng -- build --configuration=production
    
    # Check if the build succeeded by looking for the default browser output path
    if (Test-Path "dist\pulse-q\browser") {
        
        # Clean up target portal folder if it exists
        if (Test-Path "dist\$portal") {
            Remove-Item "dist\$portal" -Recurse -Force
        }
        
        # Create portal target folder
        New-Item -ItemType Directory -Path "dist\$portal" | Out-Null
        
        # Move all built files into the new portal folder
        Copy-Item -Path "dist\pulse-q\browser\*" -Destination "dist\$portal" -Recurse -Force
        
        # Copy the .htaccess file for SPA routing
        if (Test-Path ".htaccess") {
            Copy-Item ".htaccess" -Destination "dist\$portal\.htaccess" -Force
            Write-Host "[OK] Copied .htaccess to dist\$portal"
        }
        
        Write-Host "[SUCCESS] Build for $portal completed! Files are in dist\$portal" -ForegroundColor Green
        Write-Host "-----------------------------------------"
    } else {
        Write-Host "[ERROR] Build for $portal failed!" -ForegroundColor Red
        Write-Host "-----------------------------------------"
    }
}

# Restore the original environment.ts
if (Test-Path "src\environments\environment.backup.ts") {
    Copy-Item "src\environments\environment.backup.ts" -Destination "src\environments\environment.ts" -Force
    Remove-Item "src\environments\environment.backup.ts" -Force
}

Write-Host "All builds finished! Check the 'dist' folder."
