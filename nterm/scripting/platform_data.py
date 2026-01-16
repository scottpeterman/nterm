"""
nterm/scripting/platform_data.py

Platform configuration constants for device detection and command mapping.
"""

# =============================================================================
# Platform Detection Patterns
# =============================================================================

PLATFORM_PATTERNS = {
    'arista_eos': [
        r'Arista',
        r'vEOS',
    ],
    'cisco_ios': [
        r'Cisco IOS Software',
        r'IOS \(tm\)',
    ],
    'cisco_nxos': [
        r'Cisco Nexus',
        r'NX-OS',
    ],
    'cisco_iosxe': [
        r'Cisco IOS XE Software',
    ],
    'cisco_iosxr': [
        r'Cisco IOS XR Software',
    ],
    'juniper_junos': [
        r'JUNOS',
        r'Juniper Networks',
    ],
}


# =============================================================================
# Platform-specific Command Mappings
# =============================================================================

PLATFORM_COMMANDS = {
    'arista_eos': {
        'config': 'show running-config',
        'version': 'show version',
        'interfaces': 'show interfaces',
        'interfaces_status': 'show interfaces status',
        'interface_detail': 'show interfaces {name}',
        'neighbors_cdp': None,  # Arista doesn't support CDP by default
        'neighbors_lldp': 'show lldp neighbors detail',
        'neighbors': 'show lldp neighbors detail',  # Preferred protocol
        'routing_table': 'show ip route',
        'bgp_summary': 'show ip bgp summary',
        'bgp_neighbors': 'show ip bgp neighbors',
    },
    'cisco_ios': {
        'config': 'show running-config',
        'version': 'show version',
        'interfaces': 'show interfaces',
        'interfaces_status': 'show interfaces status',
        'interface_detail': 'show interfaces {name}',
        'neighbors_cdp': 'show cdp neighbors detail',
        'neighbors_lldp': 'show lldp neighbors detail',
        'neighbors': 'show cdp neighbors detail',  # Preferred protocol
        'routing_table': 'show ip route',
        'bgp_summary': 'show ip bgp summary',
        'bgp_neighbors': 'show ip bgp neighbors',
    },
    'cisco_iosxe': {
        'config': 'show running-config',
        'version': 'show version',
        'interfaces': 'show interfaces',
        'interfaces_status': 'show interfaces status',
        'interface_detail': 'show interfaces {name}',
        'neighbors_cdp': 'show cdp neighbors detail',
        'neighbors_lldp': 'show lldp neighbors detail',
        'neighbors': 'show cdp neighbors detail',
        'routing_table': 'show ip route',
        'bgp_summary': 'show ip bgp summary',
        'bgp_neighbors': 'show ip bgp neighbors',
    },
    'cisco_nxos': {
        'config': 'show running-config',
        'version': 'show version',
        'interfaces': 'show interface',
        'interfaces_status': 'show interface status',
        'interface_detail': 'show interface {name}',
        'neighbors_cdp': 'show cdp neighbors detail',
        'neighbors_lldp': 'show lldp neighbors detail',
        'neighbors': 'show cdp neighbors detail',
        'routing_table': 'show ip route',
        'bgp_summary': 'show ip bgp summary',
        'bgp_neighbors': 'show ip bgp neighbors',
    },
    'cisco_iosxr': {
        'config': 'show running-config',
        'version': 'show version',
        'interfaces': 'show interfaces',
        'interfaces_status': 'show interfaces summary',
        'interface_detail': 'show interfaces {name}',
        'neighbors_cdp': 'show cdp neighbors detail',
        'neighbors_lldp': 'show lldp neighbors detail',
        'neighbors': 'show cdp neighbors detail',
        'routing_table': 'show route',
        'bgp_summary': 'show bgp summary',
        'bgp_neighbors': 'show bgp neighbors',
    },
    'juniper_junos': {
        'config': 'show configuration',
        'version': 'show version',
        'interfaces': 'show interfaces',
        'interfaces_status': 'show interfaces terse',
        'interface_detail': 'show interfaces {name} extensive',
        'neighbors_cdp': None,  # Juniper doesn't support CDP
        'neighbors_lldp': 'show lldp neighbors',
        'neighbors': 'show lldp neighbors',
        'routing_table': 'show route',
        'bgp_summary': 'show bgp summary',
        'bgp_neighbors': 'show bgp neighbor',
    },
}

DEFAULT_COMMANDS = {
    'config': 'show running-config',
    'version': 'show version',
    'interfaces': 'show interfaces',
    'interfaces_status': 'show interfaces status',
    'interface_detail': 'show interfaces {name}',
    'neighbors_cdp': 'show cdp neighbors detail',
    'neighbors_lldp': 'show lldp neighbors detail',
    'neighbors': 'show cdp neighbors detail',
    'routing_table': 'show ip route',
    'bgp_summary': 'show ip bgp summary',
    'bgp_neighbors': 'show ip bgp neighbors',
}


# =============================================================================
# Vendor Field Mappings for Output Normalization
# =============================================================================

# Maps canonical field names to vendor-specific template field names
INTERFACE_DETAIL_FIELD_MAP = {
    'arista_eos': {
        'interface': ['INTERFACE'],
        'admin_state': ['LINK_STATUS'],
        'oper_state': ['PROTOCOL_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH'],
        'in_packets': ['INPUT_PACKETS'],
        'out_packets': ['OUTPUT_PACKETS'],
        'in_errors': ['INPUT_ERRORS'],
        'out_errors': ['OUTPUT_ERRORS'],
        'crc_errors': ['CRC'],
    },
    'cisco_ios': {
        'interface': ['INTERFACE'],
        'admin_state': ['LINK_STATUS'],
        'oper_state': ['PROTOCOL_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH'],
        'duplex': ['DUPLEX'],
        'speed': ['SPEED'],
        'in_packets': ['INPUT_PACKETS'],
        'out_packets': ['OUTPUT_PACKETS'],
        'in_errors': ['INPUT_ERRORS'],
        'out_errors': ['OUTPUT_ERRORS'],
        'crc_errors': ['CRC'],
    },
    'cisco_nxos': {
        'interface': ['INTERFACE'],
        'admin_state': ['ADMIN_STATE', 'LINK_STATUS'],
        'oper_state': ['OPER_STATE', 'PROTOCOL_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS', 'ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH', 'BW'],
        'in_packets': ['IN_PKTS', 'INPUT_PACKETS'],
        'out_packets': ['OUT_PKTS', 'OUTPUT_PACKETS'],
        'in_errors': ['IN_ERRORS', 'INPUT_ERRORS'],
        'out_errors': ['OUT_ERRORS', 'OUTPUT_ERRORS'],
        'crc_errors': ['CRC', 'CRC_ERRORS'],
    },
    'juniper_junos': {
        'interface': ['INTERFACE'],
        'admin_state': ['ADMIN_STATE'],
        'oper_state': ['LINK_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH'],
        'in_packets': ['INPUT_PACKETS'],
        'out_packets': ['OUTPUT_PACKETS'],
        'in_errors': ['INPUT_ERRORS'],
        'out_errors': ['OUTPUT_ERRORS'],
        'crc_errors': ['CRC'],
    },
}

DEFAULT_FIELD_MAP = {
    'interface': ['INTERFACE', 'PORT', 'NAME'],
    'admin_state': ['ADMIN_STATE', 'LINK_STATUS', 'STATUS'],
    'oper_state': ['OPER_STATE', 'PROTOCOL_STATUS', 'LINE_STATUS'],
    'hardware': ['HARDWARE_TYPE', 'HARDWARE', 'MEDIA_TYPE', 'TYPE'],
    'mac_address': ['MAC_ADDRESS', 'ADDRESS', 'MAC'],
    'description': ['DESCRIPTION', 'NAME', 'DESC'],
    'mtu': ['MTU'],
    'bandwidth': ['BANDWIDTH', 'BW', 'SPEED'],
    'duplex': ['DUPLEX'],
    'speed': ['SPEED'],
    'in_packets': ['INPUT_PACKETS', 'IN_PKTS', 'IN_PACKETS'],
    'out_packets': ['OUTPUT_PACKETS', 'OUT_PKTS', 'OUT_PACKETS'],
    'in_errors': ['INPUT_ERRORS', 'IN_ERRORS'],
    'out_errors': ['OUTPUT_ERRORS', 'OUT_ERRORS'],
    'crc_errors': ['CRC', 'CRC_ERRORS'],
}

# Version output field mappings
VERSION_FIELD_MAP = {
    'arista_eos': {
        'version': ['VERSION', 'version'],
        'hardware': ['HARDWARE', 'hardware', 'MODEL', 'model'],
        'serial': ['SERIAL', 'serial', 'SERIAL_NUMBER'],
        'uptime': ['UPTIME', 'uptime'],
        'hostname': ['HOSTNAME', 'hostname'],
    },
    'cisco_ios': {
        'version': ['VERSION', 'version', 'SOFTWARE', 'software'],
        'hardware': ['HARDWARE', 'hardware', 'MODEL', 'model', 'PLATFORM'],
        'serial': ['SERIAL', 'serial', 'SERIAL_NUMBER', 'serial_number'],
        'uptime': ['UPTIME', 'uptime'],
        'hostname': ['HOSTNAME', 'hostname'],
    },
    'cisco_nxos': {
        'version': ['VERSION', 'version', 'OS', 'os'],
        'hardware': ['HARDWARE', 'hardware', 'PLATFORM', 'platform'],
        'serial': ['SERIAL', 'serial'],
        'uptime': ['UPTIME', 'uptime'],
        'hostname': ['HOSTNAME', 'hostname', 'DEVICE_NAME'],
    },
    'juniper_junos': {
        'version': ['VERSION', 'version', 'JUNOS'],
        'hardware': ['HARDWARE', 'hardware', 'MODEL', 'model'],
        'serial': ['SERIAL', 'serial', 'SERIAL_NUMBER'],
        'uptime': ['UPTIME', 'uptime'],
        'hostname': ['HOSTNAME', 'hostname'],
    },
}

DEFAULT_VERSION_FIELD_MAP = {
    'version': ['VERSION', 'version', 'SOFTWARE', 'software', 'OS'],
    'hardware': ['HARDWARE', 'hardware', 'MODEL', 'model', 'PLATFORM', 'platform'],
    'serial': ['SERIAL', 'serial', 'SERIAL_NUMBER', 'serial_number'],
    'uptime': ['UPTIME', 'uptime'],
    'hostname': ['HOSTNAME', 'hostname', 'DEVICE_NAME'],
}

# Neighbor (CDP/LLDP) field mappings
NEIGHBOR_FIELD_MAP = {
    'local_interface': ['LOCAL_INTERFACE', 'local_port', 'LOCAL_PORT'],
    'neighbor_device': ['NEIGHBOR_NAME', 'DESTINATION_HOST', 'SYSTEM_NAME', 'neighbor', 'NEIGHBOR'],
    'neighbor_interface': ['NEIGHBOR_INTERFACE', 'remote_port', 'REMOTE_PORT', 'PORT_ID'],
    'platform': ['PLATFORM', 'platform', 'SYSTEM_DESCRIPTION'],
    'ip_address': ['MANAGEMENT_IP', 'IP_ADDRESS', 'ip_address'],
}