# -----------------------------------------------------------------------------
# SCRIPT: GeoLocator.py
# DESCRIPTION: First validates that location is enabled, checks Wi-Fi and 
#              Airplane Mode status, then retrieves geolocation and reverse
#              geocodes the coordinates into a human-readable address.
# REQUIREMENTS: Windows Location Services must be enabled and permission granted.
# -----------------------------------------------------------------------------

import sys
import ctypes
import winreg
import subprocess
import json
import requests
import datetime
import platform

def print_header(title):
    print()
    print("=" * 31)
    print(f"{title.center(31)}")
    print("=" * 31)
    print()

def color(text, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "cyan": "\033[96m", "magenta": "\033[95m", "reset": "\033[0m"
    }
    if sys.stdout.isatty():
        return f"{colors.get(color, '')}{text}{colors['reset']}"
    return text

def check_registry_key(path, value_name):
    try:
        hive, subkey = path.split("\\", 1)
        hive = getattr(winreg, hive)
        with winreg.OpenKey(hive, subkey) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return True, value
    except FileNotFoundError:
        return False, None
    except OSError:
        return True, None

def count_visible_networks():
    try:
        result = subprocess.run([
            "netsh", "wlan", "show", "networks"
        ], capture_output=True, text=True, timeout=5)
        output = result.stdout
        return output.count("SSID ")
    except Exception:
        return 0

def check_wifi_status():
    try:
        result = subprocess.run([
            "netsh", "wlan", "show", "interfaces"
        ], capture_output=True, text=True, timeout=5)
        output = result.stdout
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if "Radio status" in line:
                for j in range(i+1, min(i+11, len(lines))):
                    l = lines[j].strip()
                    if l.lower().startswith("software"):
                        if ':' in l:
                            radio_sw = l.split(":",1)[-1].strip()
                        else:
                            radio_sw = l.split(None, 1)[-1].strip()
                        return radio_sw == "On"
                break
    except Exception:
        pass
    return False

def check_airplane_mode():
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\RadioManagement\SystemRadioState")
        val, _ = winreg.QueryValueEx(key, "")
        return int(val) == 1
    except Exception:
        return False

def get_location():
    # Use Windows Location API via ctypes
    # This is a minimal approach using COM interfaces
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = locator.ConnectServer(".", "root\\CIMV2")
        query = "SELECT * FROM Win32_Location"
        locations = service.ExecQuery(query)
        for loc in locations:
            if hasattr(loc, "Latitude") and hasattr(loc, "Longitude"):
                return float(loc.Latitude), float(loc.Longitude)
    except Exception:
        pass
    # Fallback: Use GeoCoordinateWatcher via .NET (if available)
    try:
        import clr
        clr.AddReference("System.Device")
        from System.Device.Location import GeoCoordinateWatcher
        watcher = GeoCoordinateWatcher()
        watcher.Start()
        import time
        for _ in range(20):
            if watcher.Status.ToString() == "Ready":
                coord = watcher.Position.Location
                if not coord.IsUnknown:
                    return float(coord.Latitude), float(coord.Longitude)
            time.sleep(0.25)
    except Exception:
        pass
    return None, None

def reverse_geocode(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        headers = {"User-Agent": "Python Script (Personal Use)"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("display_name", "Unknown")
    except Exception:
        pass
    return "Address resolution failed (API error)."

def main():
    print_header("Diagnostics")
    # Registry checks
    loc_exists, disable_loc = check_registry_key(
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors", "DisableLocation")
    app_exists, let_apps = check_registry_key(
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsAccessLocation")
    location_enabled = (not loc_exists or disable_loc is None or disable_loc == 0)
    wifi_enabled = check_wifi_status()
    ssid_count = count_visible_networks() if wifi_enabled else 0
    wifi_status = "Enabled/Available" if wifi_enabled else "Not available or disabled"
    wifi_color = "green" if wifi_enabled else "red"
    airplane_on = check_airplane_mode()
    airplane_status = "Enabled" if airplane_on else "Disabled"
    airplane_color = "red" if airplane_on else "green"
    location_status = "Enabled" if location_enabled else "Disabled"
    location_color = "green" if location_enabled else "red"
    print(f"{'Location Services':<22}: {color(location_status, location_color)}")
    print(f"{'Wi-Fi':<22}: {color(wifi_status, wifi_color)}")
    print(f"{'Visible Network Count':<22}: {color(str(ssid_count), 'green')}")
    print(f"{'Airplane Mode':<22}: {color(airplane_status, airplane_color)}")
    print()
    if not wifi_enabled or airplane_on:
        print(color("Unable to perform Wi-Fi triangulation. GeoLocation will be based off of IP address. Accuracy may vary.", "yellow"))
    if not location_enabled:
        print(color("Unable to launch GeoLocator due to location permissions. Please verify that location permissions and services are enabled before trying again.", "red"))
        print_header("Location Permissions")
        if loc_exists:
            print(color(f"Registry key exists: HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\LocationAndSensors", "green"))
            if disable_loc is not None:
                if disable_loc == 0:
                    print(color("DisableLocation: 0 (Location services enabled)", "green"))
                else:
                    print(color("DisableLocation: 1 (Location services disabled)", "red"))
            else:
                print(color("DisableLocation value is missing", "yellow"))
        else:
            print(color("Registry key missing: HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\LocationAndSensors", "red"))
        if app_exists:
            print(color(f"Registry key exists: HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppPrivacy", "green"))
            if let_apps is not None:
                if let_apps == 1:
                    print(color("LetAppsAccessLocation: 1 (Enabled)", "green"))
                else:
                    print(color(f"LetAppsAccessLocation: {let_apps} (Disabled)", "red"))
            else:
                print(color("LetAppsAccessLocation value is missing", "yellow"))
        else:
            print(color("Registry key missing: HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppPrivacy", "red"))
        return
    print_header("GeoLocator Results")
    lat, lon = get_location()
    if lat is not None and lon is not None:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{'Latitude':<22}: {color(str(lat), 'magenta')}")
        print(f"{'Longitude':<22}: {color(str(lon), 'magenta')}")
        print(f"{'Timestamp':<22}: {color(timestamp, 'magenta')}")
        address = reverse_geocode(lat, lon)
        gmaps = f"https://www.google.com/maps?q={lat},{lon}"
        print(f"{'Resolved Address':<22}: {color(address, 'cyan')}")
        print(f"{'Google Maps Link':<22}: {color(gmaps, 'cyan')}")
    else:
        print(color("GPS coordinates could not be resolved or are unknown.", "yellow"))

if __name__ == "__main__":
    main()
