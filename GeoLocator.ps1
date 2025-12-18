# -----------------------------------------------------------------------------
# SCRIPT: GeoLocator.ps1
# DESCRIPTION: First validates that location is enabled, checks Wi-Fi and 
#              Airplane Mode status, then retrieves geolocation and reverse
#              geocodes the coordinates into a human-readable address.
# REQUIREMENTS: Windows Location Services must be enabled and permission granted.
# -----------------------------------------------------------------------------

# 1. Diagnostic Checks - Verify prerequisites

Write-Host ""
Write-Host "===============================" -ForegroundColor Cyan
Write-Host "           Diagnostics         " -ForegroundColor Cyan
Write-Host "===============================" -ForegroundColor Cyan
Write-Host ""

# Check Location Enable/Disable status
$locPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors'
$locationEnabled = $true
if (Test-Path $locPath) {
    $locProps = Get-ItemProperty -Path $locPath -ErrorAction SilentlyContinue
    if ($null -ne $locProps -and $locProps.PSObject.Properties.Name -contains 'DisableLocation') {
        $disable = [int]$locProps.DisableLocation
        if ($disable -ne 0) {
            $locationEnabled = $false
        }
    }
}

# Check AppPrivacy LetAppsAccessLocation
$appPrivPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy'
if (Test-Path $appPrivPath) {
    $appProps = Get-ItemProperty -Path $appPrivPath -ErrorAction SilentlyContinue
}

# Check Wi-Fi status
$wifiEnabled = $false
try {
    $netshOutput = netsh wlan show interfaces 2>$null
    if ($LASTEXITCODE -eq 0 -and $netshOutput) {
        if ($netshOutput -match 'Radio status' -and $netshOutput -match 'Hardware On' -and $netshOutput -match 'Software On') {
            $wifiEnabled = $true
        }
        elseif ($netshOutput -match 'State\s*:\s*connected') {
            $wifiEnabled = $true
        }
    }
}
catch { }
if (-not $wifiEnabled) {
    $adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceDescription -match 'Wireless' -or $_.Name -match 'Wi-Fi' -or $_.Name -match 'Wireless' }
    if ($null -ne $adapters) {
        foreach ($a in $adapters) {
            if ($a.Status -eq 'Up') {
                $wifiEnabled = $true
                break
            }
        }
    }
}

$ssidCount = 0
if ($wifiEnabled) {
        $wifiStatus = 'Enabled/Available'
        $wifiColor = 'Green'
    try {
        $netshNetworks = netsh wlan show networks 2>$null
        if ($netshNetworks) {
            $ssidCount = ($netshNetworks | Select-String -Pattern '^SSID\s+\d+\s+:' | Measure-Object).Count
        }
    }
    catch { $ssidCount = 0 }
} else {
    $wifiStatus = 'Not available or disabled'
    $wifiColor = 'Red'
}

# Check Airplane Mode status
$radioReg = 'HKLM:\System\CurrentControlSet\Control\RadioManagement\SystemRadioState'
$airplaneOn = $false
if (Test-Path $radioReg) {
    $reg = Get-ItemProperty -Path $radioReg -ErrorAction SilentlyContinue
    if ($null -ne $reg) {
        if ($reg.PSObject.Properties.Name -contains '(default)') {
            $val = $reg.'(default)'
        }
        elseif ($reg.PSObject.Properties.Name -contains '') {
            $val = $reg.''
        }
        else {
            $val = $null
        }
        if ($null -ne $val -and [int]$val -eq 1) {
            $airplaneOn = $true
        }
    }
}



$airplaneStatus = if ($airplaneOn) { 'Enabled' } else { 'Disabled' }
$airplaneColor = if ($airplaneOn) { 'Red' } else { 'Green' }

Write-Host ""
$locationStatus = if ($locationEnabled) { 'Enabled' } else { 'Disabled' }
$locationColor = if ($locationEnabled) { 'Green' } else { 'Red' }
Write-Host ("{0,-22}: {1}" -f 'Location Services', $locationStatus) -ForegroundColor $locationColor
Write-Host ("{0,-22}: {1}" -f 'Wi-Fi', $wifiStatus) -ForegroundColor $wifiColor
Write-Host ("{0,-22}: {1}" -f 'Visible Network Count', $ssidCount) -ForegroundColor Green
Write-Host ("{0,-22}: {1}" -f 'Airplane Mode', $airplaneStatus) -ForegroundColor $airplaneColor
Write-Host ""

# Warn if Wi-Fi is disabled or Airplane Mode is enabled
if (-not $wifiEnabled -or $airplaneOn) {
    Write-Host "Unable to perform Wi-Fi triangulation. GeoLocation will be based off of IP address. Accuracy may vary." -ForegroundColor Yellow
}

# If location services are disabled, do not attempt to launch GeoLocator
if (-not $locationEnabled) {
    Write-Host "Unable to launch GeoLocator due to location permissions. Please verify that location permissions and services are enabled before trying again." -ForegroundColor Red

    # Location Permissions Section Header
    Write-Host ""
    Write-Host "===============================" -ForegroundColor Cyan
    Write-Host "      Location Permissions     " -ForegroundColor Cyan
    Write-Host "===============================" -ForegroundColor Cyan
    Write-Host ""

    $locPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors'
    if (Test-Path $locPath) {
        Write-Host "Registry key exists: $locPath" -ForegroundColor Green
        $locProps = Get-ItemProperty -Path $locPath -ErrorAction SilentlyContinue
        if ($null -ne $locProps -and $locProps.PSObject.Properties.Name -contains 'DisableLocation') {
            $disable = [int]$locProps.DisableLocation
            if ($disable -eq 0) {
                Write-Host "DisableLocation: 0 (Location services enabled)" -ForegroundColor Green
            } else {
                Write-Host "DisableLocation: 1 (Location services disabled)" -ForegroundColor Red
            }
        } else {
            Write-Host "DisableLocation value is missing (default: enabled)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Registry key missing: $locPath (default: enabled)" -ForegroundColor Red
    }

    $appPrivPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy'
    if (Test-Path $appPrivPath) {
        Write-Host "Registry key exists: $appPrivPath" -ForegroundColor Green
        $appProps = Get-ItemProperty -Path $appPrivPath -ErrorAction SilentlyContinue
        if ($null -ne $appProps -and $appProps.PSObject.Properties.Name -contains 'LetAppsAccessLocation') {
            $val = [int]$appProps.LetAppsAccessLocation
            if ($val -eq 1) {
                Write-Host "LetAppsAccessLocation: 1 (Enabled)" -ForegroundColor Green
            } else {
                Write-Host "LetAppsAccessLocation: $val (Disabled)" -ForegroundColor Red
            }
        } else {
            Write-Host "LetAppsAccessLocation value is missing" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Registry key missing: $appPrivPath" -ForegroundColor Red
    }

    return
}

# 2. Load the necessary .NET Assembly for Geolocation services
try {
    Add-Type -AssemblyName System.Device
}
catch {
    Write-Error "Failed to load System.Device assembly. Geolocation services may be unavailable."
    exit 1
}

# 3. Initialize the GeoLocator
$GeoLocator = New-Object System.Device.Location.GeoCoordinateWatcher
$TimeoutSeconds = 5 # Set a maximum wait time
$StartTime = Get-Date

Write-Host "Starting GeoLocator. Waiting up to $TimeoutSeconds seconds for coordinates..."

# Start the locator
$GeoLocator.Start()

# 4. Wait for the locator to become ready, checking status and permissions
$IsReady = $false
$permissionDenied = $false
while ((Get-Date) -le ($StartTime).AddSeconds($TimeoutSeconds)) {
    if ($GeoLocator.Status -eq 'Ready') {
        $IsReady = $true
        break
    }
    if ($GeoLocator.Permission -eq 'Denied') {
        # Do not exit here. Record that permission was denied so we can
        # finish diagnostics and exit gracefully later.
        $permissionDenied = $true
        Write-Host "Location services: Disabled"
        break
    }
    Start-Sleep -Milliseconds 250
}

# Define status messages for better error reporting
$statusMap = @{
    'Disabled'       = "Location access has been disabled in system settings."
    'NotInitialized' = "Location provider is initializing."
    'NoData'         = "Location provider is not returning data."
    'Unknown'        = "Location status is unknown."
    'Denied'         = "Location access was explicitly denied by the user/system."
}

# 5. Process the Location Data and Resolve Address
if ($permissionDenied) {
    # Permission was denied by the system/user. Stop locator and inform the user.
    try { $GeoLocator.Stop() } catch { }
    Write-Host "Unable to start GeoLocator. Please check Location Services Permissions and try again."
}
elseif (-not $IsReady) {
    $currentStatus = $GeoLocator.Status
    $errorMessage = $statusMap[$currentStatus]
    if (-not $errorMessage) {
        $errorMessage = "Timed out waiting for GPS coordinates. Status: $currentStatus"
    }
    Write-Warning $errorMessage
}
else {
    $location = $GeoLocator.Position.Location

    if ($null -ne $location -and $location.IsUnknown -eq $false) {
        $latitude = $location.Latitude
        $longitude = $location.Longitude
        # Use ISO 8601 format for robust timestamps
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        Write-Host ""
        Write-Host "===============================" -ForegroundColor Cyan
        Write-Host "      GeoLocator Results    " -ForegroundColor Cyan
        Write-Host "===============================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host ("{0,-22}: {1}" -f 'Latitude', $latitude) -ForegroundColor Magenta
        Write-Host ("{0,-22}: {1}" -f 'Longitude', $longitude) -ForegroundColor Magenta
        Write-Host ("{0,-22}: {1}" -f 'Timestamp', $timestamp) -ForegroundColor Magenta

        # 6. Reverse Geocode Coordinates using OpenStreetMap Nominatim
        try {
            # The URL for the Nominatim reverse lookup
            $nominatimUrl = "https://nominatim.openstreetmap.org/reverse?format=json&lat=$latitude&lon=$longitude"

            # Use a User-Agent header as a courtesy to public APIs
            $headers = @{'User-Agent' = 'PowerShell Script (Personal Use)' }

            # Fetch location data from the API
            $locationData = Invoke-RestMethod -Uri $nominatimUrl -Headers $headers -ErrorAction Stop

            $locationName = $locationData.display_name
            $googleMapsUrl = "https://www.google.com/maps?q=$latitude,$longitude"

            Write-Host ("{0,-22}: {1}" -f 'Resolved Address', $locationName) -ForegroundColor Cyan
            Write-Host ("{0,-22}: {1}" -f 'Google Maps Link', $googleMapsUrl) -ForegroundColor Cyan

            # Only output formatted results above; do not emit PSCustomObject
        }
        catch {
            Write-Warning "Could not resolve address via Nominatim API. Error: $($_.Exception.Message)"
            Write-Host ("{0,-22}: {1}" -f 'Resolved Address', 'Address resolution failed (API error).') -ForegroundColor Red
            Write-Host ("{0,-22}: {1}" -f 'Google Maps Link', "https://www.google.com/maps?q=$latitude,$longitude") -ForegroundColor Cyan
            # Only output formatted results above; do not emit PSCustomObject
        }
    }
    else {
        Write-Warning 'GPS coordinates could not be resolved or are unknown.'
    }
}

# Stop the locator to free resources
$GeoLocator.Stop()
