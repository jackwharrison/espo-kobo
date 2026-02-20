"""
EspoCRM API User Setup

Automatically creates a role and API user for Kobo Connect integration.
"""

import requests
import json


def create_api_role_for_entity(espo_url, espo_username, espo_password, entity_name):
    """
    Create a role in EspoCRM that can create records in the specified entity.
    
    Args:
        espo_url: EspoCRM instance URL
        espo_username: Admin username
        espo_password: Admin password
        entity_name: Entity name (without C prefix, e.g., 'ChadDemo')
    
    Returns:
        dict with role details including 'id'
    """
    role_name = f"{entity_name}API"
    
    # Build the data payload with create permission for the entity
    # Include all standard entities with no permissions
    data_permissions = {
        entity_name: {
            "create": "yes",
            "read": "no",
            "edit": "no",
            "delete": "no",
            "stream": "no"
        }
    }
    
    # Add empty permissions for common entities
    common_entities = [
        "Email", "Team", "User", "Account", "Call", "Campaign", "Case", 
        "Contact", "DocumentFolder", "Document", "KnowledgeBaseArticle", 
        "KnowledgeBaseCategory", "Lead", "Meeting", "Opportunity", 
        "TargetListCategory", "TargetList", "Task", "BpmnFlowchart", 
        "BpmnUserTask", "BpmnProcess", "ReportCategory", "Report"
    ]
    
    field_data = {}
    for entity in common_entities:
        field_data[entity] = {}
    field_data[entity_name] = {}
    
    payload = {
        "assignmentPermission": "not-set",
        "userPermission": "not-set",
        "messagePermission": "not-set",
        "portalPermission": "not-set",
        "groupEmailAccountPermission": "not-set",
        "exportPermission": "not-set",
        "massUpdatePermission": "not-set",
        "dataPrivacyPermission": "not-set",
        "followerManagementPermission": "not-set",
        "auditPermission": "not-set",
        "mentionPermission": "not-set",
        "userCalendarPermission": "not-set",
        "name": role_name,
        "data": data_permissions,
        "fieldData": field_data
    }
    
    print(f"\nCreating API role: {role_name}")
    
    response = requests.post(
        f"{espo_url}/api/v1/Role",
        json=payload,
        auth=(espo_username, espo_password),
        headers={'Content-Type': 'application/json'},
        timeout=30
    )
    
    response.raise_for_status()
    role = response.json()
    
    print(f"✓ Role created successfully")
    print(f"  Role ID: {role.get('id')}")
    print(f"  Role Name: {role.get('name')}")
    
    return role


def create_api_user_for_role(espo_url, espo_username, espo_password, entity_name, role_id):
    """
    Create an API user in EspoCRM with the specified role.
    
    Args:
        espo_url: EspoCRM instance URL
        espo_username: Admin username
        espo_password: Admin password
        entity_name: Entity name (for username generation)
        role_id: Role ID to assign to this user
    
    Returns:
        dict with user details including 'id'
    """
    username = f"{entity_name.lower()}api"
    
    payload = {
        "type": "api",
        "isActive": True,
        "avatarId": None,
        "deleteId": "0",
        "userName": username,
        "teamsIds": [],
        "teamsNames": {},
        "teamsColumns": {},
        "defaultTeamName": None,
        "defaultTeamId": None,
        "rolesIds": [role_id],
        "rolesNames": {role_id: f"{entity_name}API"},
        "authMethod": "ApiKey"
    }
    
    print(f"\nCreating API user: {username}")
    
    response = requests.post(
        f"{espo_url}/api/v1/User",
        json=payload,
        auth=(espo_username, espo_password),
        headers={'Content-Type': 'application/json'},
        timeout=30
    )
    
    response.raise_for_status()
    user = response.json()
    
    print(f"✓ API user created successfully")
    print(f"  User ID: {user.get('id')}")
    print(f"  Username: {user.get('userName')}")
    
    return user


def get_api_key_for_user(espo_url, espo_username, espo_password, user_id):
    """
    Retrieve the API key for a user.
    
    Args:
        espo_url: EspoCRM instance URL
        espo_username: Admin username
        espo_password: Admin password
        user_id: User ID
    
    Returns:
        str: API key
    """
    print(f"\nRetrieving API key for user {user_id}...")
    
    response = requests.get(
        f"{espo_url}/api/v1/User/{user_id}",
        auth=(espo_username, espo_password),
        timeout=30
    )
    
    response.raise_for_status()
    user_data = response.json()
    
    api_key = user_data.get('apiKey')
    
    if not api_key:
        raise Exception("API key not found in user data")
    
    print(f"✓ API key retrieved successfully")
    print(f"  API Key: {api_key[:10]}..." if len(api_key) > 10 else f"  API Key: {api_key}")
    
    return api_key


def setup_api_user_for_entity(espo_url, espo_username, espo_password, entity_name):
    """
    Complete workflow: Create role, create user, get API key.
    
    Args:
        espo_url: EspoCRM instance URL
        espo_username: Admin username
        espo_password: Admin password
        entity_name: Entity name (without C prefix)
    
    Returns:
        dict with role_id, user_id, and api_key
    """
    print(f"\n{'='*80}")
    print(f"SETTING UP API USER FOR ENTITY: {entity_name}")
    print(f"{'='*80}")
    
    try:
        # Step 1: Create role
        role = create_api_role_for_entity(espo_url, espo_username, espo_password, entity_name)
        role_id = role.get('id')
        
        # Step 2: Create API user
        user = create_api_user_for_role(espo_url, espo_username, espo_password, entity_name, role_id)
        user_id = user.get('id')
        
        # Step 3: Get API key
        api_key = get_api_key_for_user(espo_url, espo_username, espo_password, user_id)
        
        print(f"\n{'='*80}")
        print(f"API USER SETUP COMPLETE")
        print(f"{'='*80}")
        print(f"Role: {entity_name}API (ID: {role_id})")
        print(f"User: {entity_name.lower()}api (ID: {user_id})")
        print(f"API Key: {api_key}")
        print(f"{'='*80}\n")
        
        return {
            'role_id': role_id,
            'role_name': f"{entity_name}API",
            'user_id': user_id,
            'username': f"{entity_name.lower()}api",
            'api_key': api_key
        }
    
    except requests.exceptions.HTTPError as e:
        error_msg = f"EspoCRM API error: {e.response.status_code}"
        try:
            error_detail = e.response.json()
            error_msg += f" - {error_detail}"
        except:
            error_msg += f" - {e.response.text[:200]}"
        
        print(f"\n✗ Error: {error_msg}")
        raise Exception(error_msg)
    
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        raise


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 5:
        print("Usage: python espo_api_user_setup.py ESPO_URL USERNAME PASSWORD ENTITY_NAME")
        print("\nExample:")
        print("  python espo_api_user_setup.py http://20.56.35.22 admin password123 ChadDemo")
        sys.exit(1)
    
    espo_url = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    entity_name = sys.argv[4]
    
    result = setup_api_user_for_entity(espo_url, username, password, entity_name)
    
    print("\nYou can now use this API key in Kobo Connect:")
    print(f"  API Key: {result['api_key']}")