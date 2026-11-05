"""Per-mode connection settings and a read-only ZeroTier adapter check."""
import ipaddress
import json
import subprocess
import sys

MODES = ('direct', 'zerotier')
PROFILE_DEFAULT = {'server_host': '', 'server_port': 47653, 'fingerprint': '', 'host_mode': False, 'ipv6_enabled': False}


def load_profiles(settings):
    profiles = {mode: dict(PROFILE_DEFAULT) for mode in MODES}
    # Preserve installations created before connection modes were introduced.
    profiles['direct'].update({key: settings[key] for key in PROFILE_DEFAULT if key in settings})
    stored = settings.get('connection_profiles')
    if isinstance(stored, dict):
        for mode in MODES:
            profile = stored.get(mode)
            if isinstance(profile, dict):
                profiles[mode].update({key: profile[key] for key in PROFILE_DEFAULT if key in profile})
    return profiles


def normalize_address(mode, value):
    value = value.strip()
    if not value:
        raise ValueError('address')
    if mode == 'zerotier':
        address = ipaddress.IPv4Address(value)
        if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
            raise ValueError('address')
        return str(address)
    if mode != 'direct':
        raise ValueError('mode')
    if value.startswith('[') and value.endswith(']'):
        return str(ipaddress.IPv6Address(value[1:-1]))
    return value


def parse_zerotier_ips(output):
    if not output.strip():
        return []
    data = json.loads(output)
    if not isinstance(data, list):
        raise ValueError('Unexpected network adapter information')
    addresses = []
    for value in data:
        if not isinstance(value, str): continue
        try: address = ipaddress.IPv4Address(value)
        except (ValueError, TypeError): continue
        if not (address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast):
            if str(address) not in addresses: addresses.append(str(address))
    return addresses


def zerotier_ips():
    """Find IPv4 addresses on active adapters named or described as ZeroTier.

    This is a local adapter check, not a membership or peer-reachability test.
    """
    if sys.platform != 'win32':
        raise OSError('Windows is required for this check')
    script = r'''[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ErrorActionPreference = 'Stop'
$ips = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and ($_.Name -match 'ZeroTier' -or $_.InterfaceDescription -match 'ZeroTier') } | ForEach-Object { Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.AddressState -eq 'Preferred' } | ForEach-Object { $_.IPAddress } })
ConvertTo-Json -InputObject $ips -Compress'''
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                            capture_output=True, encoding='utf-8-sig', errors='replace', timeout=12,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    if result.returncode:
        raise OSError('Unable to inspect network adapters')
    return parse_zerotier_ips(result.stdout)


def parse_global_ipv6(output):
    if not output.strip(): return []
    data=json.loads(output)
    if not isinstance(data,list): raise ValueError('Unexpected network adapter information')
    addresses=[]
    for value in data:
        if not isinstance(value,str): continue
        try: address=ipaddress.IPv6Address(value)
        except ValueError: continue
        if address.is_global and not address.is_multicast and str(address) not in addresses:
            addresses.append(str(address))
    return addresses


def global_ipv6_addresses():
    """Inspect preferred global IPv6 addresses; this does not prove reachability."""
    if sys.platform != 'win32': raise OSError('Windows is required for this check')
    script = r'''[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ErrorActionPreference = 'Stop'
$ips = @(Get-NetIPAddress -AddressFamily IPv6 -AddressState Preferred | ForEach-Object { $_.IPAddress })
ConvertTo-Json -InputObject $ips -Compress'''
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                          capture_output=True,encoding='utf-8-sig',errors='replace',timeout=12,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
    if result.returncode: raise OSError('Unable to inspect network adapters')
    return parse_global_ipv6(result.stdout)
