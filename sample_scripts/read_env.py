"""
read_env.py - Simple API environment check

Usage in nterm IPython:
    %load sample_scripts/read_env.py
    # Execute cell (Shift+Enter), then:
    read_env(api)
"""

def read_env(api):
    """Display nterm API environment information."""
    print("\n" + "="*70)
    print("nterm API Environment")
    print("="*70 + "\n")
    
    # Get API status
    status = api.status()
    print("API Status:")
    print(f"  Devices:          {status['devices']}")
    print(f"  Folders:          {status['folders']}")
    print(f"  Credentials:      {status['credentials']}")
    print(f"  Vault unlocked:   {status['vault_unlocked']}")
    print(f"  Active sessions:  {status['active_sessions']}")
    print(f"  Parser available: {status['parser_available']}")
    
    # Get database info
    db_info = api.db_info()
    print("\nTextFSM Database:")
    print(f"  Path:        {db_info.get('db_path', 'not set')}")
    print(f"  Exists:      {db_info.get('db_exists', False)}")
    
    if db_info.get('db_exists'):
        print(f"  Size:        {db_info.get('db_size_mb', 0):.2f} MB")
        print(f"  Absolute:    {db_info.get('db_absolute_path', 'unknown')}")
    
    print("\n" + "="*70 + "\n")
    
    return db_info
