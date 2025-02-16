#!/usr/bin/env python3
import plistlib
import zipfile
import tempfile
import os
import json
import requests
from typing import Dict, Any

def extract_app_permissions(ipa_path: str) -> Dict[str, Any]:
    """Extract permissions from IPA/TIPA file"""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract IPA/TIPA
            with zipfile.ZipFile(ipa_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find Payload directory
            payload_dir = os.path.join(temp_dir, 'Payload')
            if not os.path.exists(payload_dir):
                return {"error": "No Payload directory found"}
            
            # Find .app directory
            app_dir = None
            for item in os.listdir(payload_dir):
                if item.endswith('.app'):
                    app_dir = os.path.join(payload_dir, item)
                    break
            
            if not app_dir:
                return {"error": "No .app directory found"}
            
            # Read Info.plist
            plist_path = os.path.join(app_dir, 'Info.plist')
            if not os.path.exists(plist_path):
                return {"error": "No Info.plist found"}
                
            with open(plist_path, 'rb') as f:
                plist = plistlib.load(f)
            
            # Extract permissions
            permissions = {
                "privacy": {},
                "entitlements": []
            }
            
            # Get privacy permissions
            privacy_keys = [k for k in plist.keys() if k.startswith('NS') and 'Usage' in k]
            for key in privacy_keys:
                permission_name = key.replace('NS', '').replace('UsageDescription', '')
                permissions["privacy"][permission_name] = plist[key]
            
            # Get entitlements if available
            entitlements_path = os.path.join(app_dir, 'embedded.mobileprovision')
            if os.path.exists(entitlements_path):
                # Parse entitlements from mobileprovision
                # This requires more complex parsing as it's in a special format
                pass
                
            return permissions
            
    except Exception as e:
        return {"error": str(e)}

def update_app_permissions(app_json_path: str, ipa_url: str) -> bool:
    """Update app.json with extracted permissions"""
    try:
        # Download IPA/TIPA file
        with tempfile.NamedTemporaryFile(suffix='.ipa') as temp_file:
            response = requests.get(ipa_url, stream=True)
            if response.status_code == 200:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_file.flush()
                
                # Extract permissions
                permissions = extract_app_permissions(temp_file.name)
                if "error" in permissions:
                    print(f"Error extracting permissions: {permissions['error']}")
                    return False
                
                # Update app.json
                if os.path.exists(app_json_path):
                    with open(app_json_path, 'r') as f:
                        app_data = json.load(f)
                    
                    app_data["appPermissions"] = permissions
                    
                    with open(app_json_path, 'w') as f:
                        json.dump(app_data, f, indent=2)
                    print(f"Updated appPermissions for {app_json_path}")
                    return True
                    
        print("Failed to download IPA/TIPA file or app.json does not exist.")
        return False
        
    except Exception as e:
        print(f"Error updating permissions: {str(e)}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: extract_permissions.py <path_to_ipa>")
        sys.exit(1)
        
    permissions = extract_app_permissions(sys.argv[1])
    print(json.dumps(permissions, indent=2))