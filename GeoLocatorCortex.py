# -----------------------------------------------------------------------------
# SCRIPT: GeoLocatorCortex.py
# DESCRIPTION: Due to Cortex XDR module restraints, this simply runs the PowerShell
#              script within the python script.
# REQUIREMENTS: Windows Location Services must be enabled and permission granted.
# -----------------------------------------------------------------------------
import ctypes
import sys
import time
import requests
import subprocess
import json
import winreg


# Use PowerShell to run the full GeoLocator.ps1 logic
ps_script = r'''
Write-Host ""
Write-Host "==============================="
Write-Host "           Diagnostics         "
Write-Host "==============================="
Write-Host ""

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

$appPrivPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy'
if (Test-Path $appPrivPath) {
	$appProps = Get-ItemProperty -Path $appPrivPath -ErrorAction SilentlyContinue
}

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
Write-Host ("{0,-22}: {1}" -f 'Location Services', $locationStatus)
Write-Host ("{0,-22}: {1}" -f 'Wi-Fi', $wifiStatus)
Write-Host ("{0,-22}: {1}" -f 'Visible Network Count', $ssidCount)
Write-Host ("{0,-22}: {1}" -f 'Airplane Mode', $airplaneStatus)
Write-Host ""

if (-not $wifiEnabled -or $airplaneOn) {
	Write-Host "Unable to perform Wi-Fi triangulation. GeoLocation will be based off of IP address. Accuracy may vary."
}

if (-not $locationEnabled) {
	Write-Host "Unable to launch GeoLocator due to location permissions. Please verify that location permissions and services are enabled before trying again."

	Write-Host ""
	Write-Host "==============================="
	Write-Host "      Location Permissions     "
	Write-Host "==============================="
	Write-Host ""

	$locPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors'
	if (Test-Path $locPath) {
		Write-Host "Registry key exists: $locPath"
		$locProps = Get-ItemProperty -Path $locPath -ErrorAction SilentlyContinue
		if ($null -ne $locProps -and $locProps.PSObject.Properties.Name -contains 'DisableLocation') {
			$disable = [int]$locProps.DisableLocation
			if ($disable -eq 0) {
				Write-Host "DisableLocation: 0 (Location services enabled)"
			} else {
				Write-Host "DisableLocation: 1 (Location services disabled)"
			}
		} else {
			Write-Host "DisableLocation value is missing (default: enabled)"
		}
	} else {
		Write-Host "Registry key missing: $locPath (default: enabled)"
	}

	$appPrivPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy'
	if (Test-Path $appPrivPath) {
		Write-Host "Registry key exists: $appPrivPath"
		$appProps = Get-ItemProperty -Path $appPrivPath -ErrorAction SilentlyContinue
		if ($null -ne $appProps -and $appProps.PSObject.Properties.Name -contains 'LetAppsAccessLocation') {
			$val = [int]$appProps.LetAppsAccessLocation
			if ($val -eq 1) {
				Write-Host "LetAppsAccessLocation: 1 (Enabled)"
			} else {
				Write-Host "LetAppsAccessLocation: $val (Disabled)"
			}
		} else {
			Write-Host "LetAppsAccessLocation value is missing"
		}
	} else {
		Write-Host "Registry key missing: $appPrivPath"
	}

	return
}

try {
	Add-Type -AssemblyName System.Device
}
catch {
	Write-Error "Failed to load System.Device assembly. Geolocation services may be unavailable."
	exit 1
}

$GeoLocator = New-Object System.Device.Location.GeoCoordinateWatcher
$TimeoutSeconds = 5
$StartTime = Get-Date

Write-Host "Starting GeoLocator. Waiting up to $TimeoutSeconds seconds for coordinates..."
$GeoLocator.Start()

$IsReady = $false
$permissionDenied = $false
while ((Get-Date) -le ($StartTime).AddSeconds($TimeoutSeconds)) {
	if ($GeoLocator.Status -eq 'Ready') {
		$IsReady = $true
		break
	}
	if ($GeoLocator.Permission -eq 'Denied') {
		$permissionDenied = $true
		Write-Host "Location services: Disabled"
		break
	}
	Start-Sleep -Milliseconds 250
}

$statusMap = @{
	'Disabled'       = "Location access has been disabled in system settings."
	'NotInitialized' = "Location provider is initializing."
	'NoData'         = "Location provider is not returning data."
	'Unknown'        = "Location status is unknown."
	'Denied'         = "Location access was explicitly denied by the user/system."
}

if ($permissionDenied) {
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
		$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

		Write-Host ""
		Write-Host "==============================="
		Write-Host "      GeoLocator Results    "
		Write-Host "==============================="
		Write-Host ""
		Write-Host ("{0,-22}: {1}" -f 'Latitude', $latitude)
		Write-Host ("{0,-22}: {1}" -f 'Longitude', $longitude)
		Write-Host ("{0,-22}: {1}" -f 'Timestamp', $timestamp)

		try {
			$nominatimUrl = "https://nominatim.openstreetmap.org/reverse?format=json&lat=$latitude&lon=$longitude"
			$headers = @{'User-Agent' = 'PowerShell Script (Personal Use)' }
			$locationData = Invoke-RestMethod -Uri $nominatimUrl -Headers $headers -ErrorAction Stop
			$locationName = $locationData.display_name
			$googleMapsUrl = "https://www.google.com/maps?q=$latitude,$longitude"
			Write-Host ("{0,-22}: {1}" -f 'Resolved Address', $locationName)
			Write-Host ("{0,-22}: {1}" -f 'Google Maps Link', $googleMapsUrl)
		}
		catch {
			Write-Warning "Could not resolve address via Nominatim API. Error: $($_.Exception.Message)"
			Write-Host ("{0,-22}: {1}" -f 'Resolved Address', 'Address resolution failed (API error).')
			Write-Host ("{0,-22}: {1}" -f 'Google Maps Link', "https://www.google.com/maps?q=$latitude,$longitude")
		}
	}
	else {
		Write-Warning 'GPS coordinates could not be resolved or are unknown.'
	}
}
$GeoLocator.Stop()
'''

try:
	completed = subprocess.run(
		["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
		capture_output=True, text=True, timeout=60
	)
	stdout = completed.stdout.strip()
	if not stdout:
		stdout = completed.stderr.strip()

	# Try to parse JSON output from PowerShell
	try:
		result = json.loads(stdout)
		if isinstance(result, dict) and 'error' in result:
			print(result['error'])
			sys.exit(1)
		else:
			timestamp = result.get('timestamp')
			gm = result.get('google_maps_url')
			name = result.get('location_name')
			if timestamp and gm and name:
				print(f"{timestamp} - {gm} - {name}")
			else:
				# Unexpected structure: print raw output
				print(stdout)
	except ValueError:
		# Not JSON: print raw output
		print(stdout)
	except Exception as e:
		print("Failed to parse location output:", e)
		sys.exit(1)
except subprocess.TimeoutExpired:
	print("PowerShell command timed out.")
	sys.exit(1)
except Exception as e:
	print("Failed to get location:", e)
	sys.exit(1)
