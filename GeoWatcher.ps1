# -----------------------------------------------------------------------------
# SCRIPT: Get-LocationInfo.ps1
# DESCRIPTION: Retrieves the current system geolocation (latitude and longitude),
#              then uses the Nominatim service to reverse geocode the coordinates
#              into a human-readable address.
# REQUIREMENTS: Windows Location Services must be enabled and permission granted.
# -----------------------------------------------------------------------------

# 1. Load the necessary .NET Assembly for Geolocation services
try {
    Add-Type -AssemblyName System.Device
}
catch {
    Write-Error "Failed to load System.Device assembly. Geolocation services may be unavailable."
    exit 1
}

# 2. Initialize the GeoCoordinate Watcher
$GeoWatcher = New-Object System.Device.Location.GeoCoordinateWatcher
$TimeoutSeconds = 5 # Set a maximum wait time
$StartTime = Get-Date

Write-Host "Starting location watcher. Waiting up to $TimeoutSeconds seconds for coordinates..."

# Start the watcher
$GeoWatcher.Start()

# 3. Wait for the watcher to become ready, checking status and permissions
$IsReady = $false
while ((Get-Date) -le ($StartTime).AddSeconds($TimeoutSeconds)) {
    if ($GeoWatcher.Status -eq 'Ready') {
        $IsReady = $true
        break
    }
    if ($GeoWatcher.Permission -eq 'Denied') {
        Write-Error 'Location access permission was explicitly denied by the system or user.'
        exit 1
    }
    Start-Sleep -Milliseconds 250
}

# 4. Process the Location Data and Resolve Address
if (-not $IsReady) {
    Write-Warning "Timed out waiting for GPS coordinates. Status: $($GeoWatcher.Status)"
}
elseif ($GeoWatcher.Permission -eq 'Denied') {
    # Handled above, but a final check for clarity
    Write-Error 'Location access permission was denied.'
}
else {
    $location = $GeoWatcher.Position.Location

    if ($location -ne $null -and $location.IsUnknown -eq $false) {
        $latitude = $location.Latitude
        $longitude = $location.Longitude
        # Use ISO 8601 format for robust timestamps
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        Write-Host "Coordinates found: Lat $latitude, Lon $longitude"

        # 5. Reverse Geocode Coordinates using OpenStreetMap Nominatim
        try {
            # The URL for the Nominatim reverse lookup
            $nominatimUrl = "https://nominatim.openstreetmap.org/reverse?format=json&lat=$latitude&lon=$longitude"

            # Use a User-Agent header as a courtesy to public APIs
            $headers = @{'User-Agent' = 'PowerShell Script (Personal Use)'}

            # Fetch location data from the API
            $locationData = Invoke-RestMethod -Uri $nominatimUrl -Headers $headers -ErrorAction Stop

            $locationName = $locationData.display_name
            $googleMapsUrl = "https://www.google.com/maps?q=$latitude,$longitude"

            # 6. Output the final data as a structured object
            [PSCustomObject]@{
                Timestamp      = $timestamp
                Latitude       = $latitude
                Longitude      = $longitude
                GoogleMapsLink = $googleMapsUrl
                ResolvedAddress= $locationName
            } | Write-Output
        }
        catch {
            Write-Warning "Could not resolve address via Nominatim API. Error: $($_.Exception.Message)"
            # Fallback output with available data
            [PSCustomObject]@{
                Timestamp      = $timestamp
                Latitude       = $latitude
                Longitude      = $longitude
                GoogleMapsLink = "https://www.google.com/maps?q=$latitude,$longitude"
                ResolvedAddress= "Address resolution failed (API error)."
            } | Write-Output
        }
    }
    else {
        Write-Warning 'GPS coordinates could not be resolved or are unknown.'
    }
}

# Stop the watcher to free resources
$GeoWatcher.Stop()

