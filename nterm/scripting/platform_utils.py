"""
nterm/scripting/platform_utils.py

Platform detection and field normalization utilities.
"""

import re
from typing import Optional, List, Dict, Any, Union

from .platform_data import (
    PLATFORM_PATTERNS,
    PLATFORM_COMMANDS,
    DEFAULT_COMMANDS,
    INTERFACE_DETAIL_FIELD_MAP,
    DEFAULT_FIELD_MAP,
    VERSION_FIELD_MAP,
    DEFAULT_VERSION_FIELD_MAP,
    NEIGHBOR_FIELD_MAP,
)


def detect_platform(version_output: str, tfsm_engine=None) -> Optional[str]:
    """
    Detect device platform from 'show version' output.

    Uses TextFSM template matching as primary method (more accurate),
    falls back to regex patterns if no template matches.

    Args:
        version_output: Raw output from 'show version' command
        tfsm_engine: Optional TextFSMAutoEngine instance for template-based detection

    Returns:
        Platform string (e.g., 'cisco_ios', 'arista_eos') or None if not detected
    """
    # Primary method: Use TextFSM template matching
    if tfsm_engine is not None:
        platform = detect_platform_from_template(version_output, tfsm_engine)
        if platform:
            return platform

    # Fallback: Regex pattern matching
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, version_output, re.IGNORECASE):
                return platform
    return None


def detect_platform_from_template(
    version_output: str,
    tfsm_engine,
    min_score: float = 50.0,
) -> Optional[str]:
    """
    Detect platform by finding the best matching TextFSM template.

    This is more accurate than regex because TextFSM templates are designed
    to parse specific platform outputs structurally.

    Args:
        version_output: Raw output from 'show version' or similar command
        tfsm_engine: TextFSMAutoEngine instance
        min_score: Minimum match score to accept (default 50.0)

    Returns:
        Platform string extracted from template name, or None

    Example:
        Template 'cisco_ios_show_version' → returns 'cisco_ios'
        Template 'arista_eos_show_version' → returns 'arista_eos'
    """
    if not tfsm_engine or not version_output:
        return None

    try:
        # Try with show_version filter first
        best_template, parsed_data, best_score, all_scores = tfsm_engine.find_best_template(
            device_output=version_output,
            filter_string="show_version",
        )

        if best_template and best_score >= min_score:
            platform = extract_platform_from_template_name(best_template)
            if platform:
                return platform

        # If show_version didn't match well, try without filter
        # This catches show system info, show version detail, etc.
        if not best_template or best_score < min_score:
            best_template, parsed_data, best_score, all_scores = tfsm_engine.find_best_template(
                device_output=version_output,
                filter_string="",  # No filter - let it find best match
            )

            if best_template and best_score >= min_score:
                platform = extract_platform_from_template_name(best_template)
                if platform:
                    return platform

    except Exception:
        pass  # Fall through to return None

    return None


def extract_platform_from_template_name(template_name: str) -> Optional[str]:
    """
    Extract platform identifier from a TextFSM template name.

    Template names follow the pattern: {platform}_{command}
    Examples:
        'cisco_ios_show_version' → 'cisco_ios'
        'arista_eos_show_interfaces' → 'arista_eos'
        'juniper_junos_show_version' → 'juniper_junos'
        'cisco_nxos_show_version' → 'cisco_nxos'

    Args:
        template_name: Full template name from TextFSM database

    Returns:
        Platform string or None if pattern not recognized
    """
    if not template_name:
        return None

    # Known platform prefixes (ordered by specificity - longer matches first)
    known_platforms = [
        'cisco_iosxr',
        'cisco_iosxe',
        'cisco_nxos',
        'cisco_ios',
        'cisco_asa',
        'cisco_wlc',
        'arista_eos',
        'juniper_junos',
        'juniper_screenos',
        'hp_procurve',
        'hp_comware',
        'huawei_vrp',
        'linux',
        'paloalto_panos',
        'fortinet_fortios',
        'dell_force10',
        'dell_os10',
        'extreme_exos',
        'extreme_nos',
        'brocade_fastiron',
        'brocade_netiron',
        'ubiquiti_edgeswitch',
        'mikrotik_routeros',
        'vyos',
        'alcatel_aos',
        'alcatel_sros',
        'checkpoint_gaia',
        'enterasys',
        'ruckus_fastiron',
        'yamaha',
        'zyxel_os',
    ]

    template_lower = template_name.lower()

    for platform in known_platforms:
        if template_lower.startswith(platform + '_'):
            return platform

    # Fallback: try to extract platform from template name pattern
    # Assumes format: platform_command or platform_subplatform_command
    parts = template_name.split('_')
    if len(parts) >= 2:
        # Try first two parts (handles cisco_ios, arista_eos, etc.)
        potential_platform = f"{parts[0]}_{parts[1]}"
        if potential_platform.lower() in [p.lower() for p in known_platforms]:
            return potential_platform.lower()

        # Try just first part for single-word platforms (linux, vyos)
        if parts[0].lower() in [p.lower() for p in known_platforms]:
            return parts[0].lower()

    return None


def get_platform_command(
    platform: Optional[str],
    command_type: str,
    **kwargs
) -> Optional[str]:
    """
    Get platform-specific command for a given operation.

    Args:
        platform: Platform string (e.g., 'cisco_ios') or None
        command_type: Command type (e.g., 'config', 'version', 'interfaces')
        **kwargs: Format arguments for commands with placeholders (e.g., name='Gi0/1')

    Returns:
        Command string or None if command not available for platform

    Example:
        >>> get_platform_command('cisco_ios', 'config')
        'show running-config'
        >>> get_platform_command('juniper_junos', 'config')
        'show configuration'
        >>> get_platform_command('cisco_ios', 'interface_detail', name='Gi0/1')
        'show interfaces Gi0/1'
    """
    # Get platform-specific commands or fall back to defaults
    platform_cmds = PLATFORM_COMMANDS.get(platform, {}) if platform else {}

    # Look up command type
    cmd = platform_cmds.get(command_type)
    if cmd is None:
        cmd = DEFAULT_COMMANDS.get(command_type)

    if cmd is None:
        return None

    # Apply format arguments if provided
    if kwargs:
        try:
            cmd = cmd.format(**kwargs)
        except KeyError:
            pass  # Return unformatted if missing keys

    return cmd


def get_command_alternatives(command_type: str) -> List[str]:
    """
    Get all platform variants of a command for try-until-success patterns.

    Args:
        command_type: Command type (e.g., 'neighbors')

    Returns:
        List of unique command strings across all platforms

    Example:
        >>> get_command_alternatives('neighbors')
        ['show cdp neighbors detail', 'show lldp neighbors detail', 'show lldp neighbors']
    """
    commands = set()

    # Gather from all platforms
    for platform_cmds in PLATFORM_COMMANDS.values():
        cmd = platform_cmds.get(command_type)
        if cmd:
            commands.add(cmd)

    # Add default
    default = DEFAULT_COMMANDS.get(command_type)
    if default:
        commands.add(default)

    return list(commands)


def extract_field(
    data: Dict[str, Any],
    field_names: List[str],
    default: Any = None,
    first_element: bool = True,
) -> Any:
    """
    Extract a field value trying multiple possible field names.

    Args:
        data: Dictionary to extract from (e.g., parsed command output row)
        field_names: List of possible field names in priority order
        default: Value to return if no field found
        first_element: If value is a list, return first element

    Returns:
        Field value or default

    Example:
        >>> data = {'VERSION': '15.2(4)M', 'HARDWARE': ['ISR4451']}
        >>> extract_field(data, ['version', 'VERSION', 'SOFTWARE'])
        '15.2(4)M'
        >>> extract_field(data, ['HARDWARE', 'MODEL'])
        'ISR4451'  # first_element=True extracts from list
    """
    for name in field_names:
        if name in data and data[name]:
            value = data[name]
            # Handle list values
            if first_element and isinstance(value, list):
                return value[0] if value else default
            return value
    return default


def extract_fields(
    data: Dict[str, Any],
    field_map: Dict[str, List[str]],
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extract multiple fields using a field mapping.

    Args:
        data: Dictionary to extract from
        field_map: Mapping of canonical names to possible field names
        defaults: Default values for each canonical field

    Returns:
        Dictionary with canonical field names and extracted values

    Example:
        >>> data = {'VERSION': '15.2', 'HARDWARE': 'ISR4451'}
        >>> field_map = {'version': ['VERSION', 'SOFTWARE'], 'hardware': ['HARDWARE', 'MODEL']}
        >>> extract_fields(data, field_map)
        {'version': '15.2', 'hardware': 'ISR4451'}
    """
    defaults = defaults or {}
    result = {}

    for canonical_name, possible_names in field_map.items():
        default = defaults.get(canonical_name, 'unknown')
        result[canonical_name] = extract_field(data, possible_names, default)

    return result


def extract_version_info(
    parsed_data: List[Dict[str, Any]],
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract version information from parsed 'show version' output.

    Args:
        parsed_data: Parsed output from show version command
        platform: Platform string for platform-specific field mapping

    Returns:
        Dictionary with version, hardware, serial, uptime, hostname

    Example:
        >>> result = api.send(session, "show version")
        >>> extract_version_info(result.parsed_data, session.platform)
        {'version': '15.2(4)M', 'hardware': 'ISR4451', 'serial': 'FDO2134', ...}
    """
    if not parsed_data:
        return {
            'version': 'unknown',
            'hardware': 'unknown',
            'serial': 'unknown',
            'uptime': 'unknown',
            'hostname': 'unknown',
        }

    data = parsed_data[0]  # show version typically returns single row

    # Platform-specific field mappings
    # These override the generic mappings in platform_data.py when needed
    PLATFORM_VERSION_FIELDS = {
        'arista_eos': {
            'version': ['IMAGE', 'VERSION', 'SOFTWARE_IMAGE', 'EOS_VERSION'],
            'hardware': ['MODEL', 'HARDWARE', 'PLATFORM'],
            'serial': ['SERIAL_NUMBER', 'SERIAL', 'SN'],
            'uptime': ['UPTIME'],
            'hostname': ['HOSTNAME'],
        },
        'cisco_ios': {
            'version': ['VERSION', 'SOFTWARE_VERSION', 'ROMMON'],
            'hardware': ['HARDWARE', 'MODEL', 'PLATFORM'],
            'serial': ['SERIAL', 'SERIAL_NUMBER'],
            'uptime': ['UPTIME'],
            'hostname': ['HOSTNAME'],
        },
        'cisco_nxos': {
            'version': ['OS', 'VERSION', 'NXOS_VERSION', 'KICKSTART_VERSION'],
            'hardware': ['PLATFORM', 'HARDWARE', 'CHASSIS'],
            'serial': ['SERIAL', 'SERIAL_NUMBER'],
            'uptime': ['UPTIME'],
            'hostname': ['HOSTNAME', 'DEVICE_NAME'],
        },
        'cisco_iosxe': {
            'version': ['VERSION', 'ROMMON'],
            'hardware': ['HARDWARE', 'MODEL', 'PLATFORM'],
            'serial': ['SERIAL', 'SERIAL_NUMBER'],
            'uptime': ['UPTIME'],
            'hostname': ['HOSTNAME'],
        },
        'juniper_junos': {
            'version': ['JUNOS_VERSION', 'VERSION'],
            'hardware': ['MODEL', 'HARDWARE'],
            'serial': ['SERIAL_NUMBER', 'SERIAL'],
            'uptime': ['UPTIME', 'RE_UPTIME'],
            'hostname': ['HOSTNAME'],
        },
    }

    # Default field mapping (tries common field names)
    DEFAULT_FIELDS = {
        'version': ['VERSION', 'IMAGE', 'SOFTWARE_VERSION', 'SOFTWARE_IMAGE', 'OS', 'ROMMON'],
        'hardware': ['HARDWARE', 'MODEL', 'PLATFORM', 'CHASSIS'],
        'serial': ['SERIAL', 'SERIAL_NUMBER', 'SN'],
        'uptime': ['UPTIME'],
        'hostname': ['HOSTNAME', 'DEVICE_NAME'],
    }

    # Get platform-specific mapping or fall back to defaults
    if platform and platform in PLATFORM_VERSION_FIELDS:
        field_map = PLATFORM_VERSION_FIELDS[platform]
    else:
        # Try to load from platform_data if available
        try:
            loaded_map = VERSION_FIELD_MAP.get(platform, DEFAULT_VERSION_FIELD_MAP) if platform else DEFAULT_VERSION_FIELD_MAP
            field_map = loaded_map if loaded_map else DEFAULT_FIELDS
        except (NameError, TypeError):
            field_map = DEFAULT_FIELDS

    return extract_fields(data, field_map, defaults={
        'version': 'unknown',
        'hardware': 'unknown',
        'serial': 'unknown',
        'uptime': 'unknown',
        'hostname': 'unknown',
    })


def extract_neighbor_info(
    parsed_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract neighbor information from parsed CDP/LLDP output.

    Args:
        parsed_data: Parsed output from show cdp/lldp neighbors command

    Returns:
        List of neighbor dictionaries with normalized field names
    """
    if not parsed_data:
        return []

    neighbors = []
    for row in parsed_data:
        neighbor = extract_fields(row, NEIGHBOR_FIELD_MAP, defaults={
            'local_interface': 'unknown',
            'neighbor_device': 'unknown',
            'neighbor_interface': 'unknown',
            'platform': 'unknown',
            'ip_address': '',
        })
        neighbors.append(neighbor)

    return neighbors


def normalize_fields(
    parsed_data: List[Dict[str, Any]],
    platform: str,
    field_map_dict: Dict[str, Dict[str, List[str]]],
) -> List[Dict[str, Any]]:
    """
    Normalize vendor-specific field names to canonical names.

    Args:
        parsed_data: Raw parsed data from TextFSM
        platform: Detected platform (e.g., 'cisco_ios')
        field_map_dict: Mapping dict (e.g., INTERFACE_DETAIL_FIELD_MAP)

    Returns:
        List of dicts with normalized field names

    Example:
        >>> data = [{'LINK_STATUS': 'up', 'PROTOCOL_STATUS': 'up'}]
        >>> normalize_fields(data, 'cisco_ios', INTERFACE_DETAIL_FIELD_MAP)
        [{'admin_state': 'up', 'oper_state': 'up'}]
    """
    field_map = field_map_dict.get(platform, DEFAULT_FIELD_MAP)
    normalized = []

    for row in parsed_data:
        norm_row = {}

        # Map vendor-specific fields to canonical names
        for canonical_name, vendor_names in field_map.items():
            for vendor_name in vendor_names:
                if vendor_name in row:
                    norm_row[canonical_name] = row[vendor_name]
                    break

        # Keep any fields that weren't in the mapping
        mapped_vendor_fields = {vn for vnames in field_map.values() for vn in vnames}
        for key, value in row.items():
            if key not in mapped_vendor_fields:
                norm_row[key] = value

        normalized.append(norm_row)

    return normalized


def get_paging_disable_command(platform: Optional[str]) -> Optional[str]:
    """
    Get the appropriate command to disable terminal paging for a platform.

    Args:
        platform: Detected platform string

    Returns:
        Command string or None if platform doesn't require paging disable
    """
    if not platform:
        return None

    if 'cisco' in platform:
        return "terminal length 0"
    elif platform == 'juniper_junos':
        return "set cli screen-length 0"
    elif platform == 'arista_eos':
        return "terminal length 0"

    return None


def get_paging_disable_commands_to_try() -> List[str]:
    """
    Get list of paging disable commands to try when platform is unknown.

    Returns a prioritized list of commands that cover most network platforms.
    Commands are ordered by likelihood of success across vendors.

    Returns:
        List of paging disable commands to try in order
    """
    return [
        # Cisco IOS/IOS-XE/NX-OS, Arista EOS (most common)
        "terminal length 0",
        # Cisco alternative
        "terminal pager 0",
        # Juniper JUNOS
        "set cli screen-length 0",
        # Some Cisco platforms
        "screen-length 0",
        # HP/Aruba
        "no page",
        # Huawei
        "screen-length 0 temporary",
        # Extreme
        "disable clipaging",
        # Dell/Force10
        "terminal length 0",
    ]


def try_disable_paging(shell, prompt, send_command_func, debug: bool = False) -> bool:
    """
    Try multiple commands to disable terminal paging.

    Used for auto-recovery when PagingNotDisabledError is raised.

    Args:
        shell: Active SSH channel
        prompt: Device prompt
        send_command_func: Function to send commands (ssh_connection.send_command)
        debug: Print debug info

    Returns:
        True if any command succeeded (didn't raise exception), False if all failed
    """
    commands = get_paging_disable_commands_to_try()

    for cmd in commands:
        try:
            if debug:
                print(f"[PAGING] Trying: {cmd}")
            # Short timeout - these commands should return quickly
            send_command_func(shell, cmd, prompt, timeout=5)
            if debug:
                print(f"[PAGING] Success: {cmd}")
            return True
        except Exception as e:
            if debug:
                print(f"[PAGING] Failed: {cmd} - {e}")
            continue

    return False


def sanitize_filename(name: str) -> str:
    """
    Make a device name safe for use in filenames.

    Args:
        name: Device name or identifier

    Returns:
        Sanitized string safe for filesystem use
    """
    return "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)