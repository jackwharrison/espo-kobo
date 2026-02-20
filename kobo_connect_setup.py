"""
Kobo Connect REST Service Setup

Configures Kobo REST services to use Kobo Connect as middleware to EspoCRM.
"""

import requests
import json


def setup_kobo_connect_rest_service(kobo_url, api_token, asset_id, entity_name, field_mapping, espo_url, espo_api_key):
    """
    Set up a REST service in Kobo that uses Kobo Connect to push submissions to EspoCRM.
    
    Args:
        kobo_url: Base Kobo URL (e.g., 'https://kobo.ifrc.org')
        api_token: Kobo API token
        asset_id: The form's asset ID
        entity_name: EspoCRM entity name (with C prefix, e.g., 'CChadDemo')
        field_mapping: Dict mapping Kobo field names to EspoCRM field names
            Example: {'Name': 'name', 'Date_of_Birth': 'dateOfBirth'}
        espo_url: EspoCRM instance URL (will add trailing slash if missing)
        espo_api_key: EspoCRM API key for authentication
    
    Returns:
        dict with service details
    """
    # Ensure espo_url has trailing slash
    if not espo_url.endswith('/'):
        espo_url += '/'
    
    # Build custom HTTP headers for Kobo Connect
    # Format: Kobo_field_name -> EntityName.espoFieldName
    custom_headers = {}
    for kobo_field, espo_field in field_mapping.items():
        header_key = kobo_field.replace(' ', '_')  # Replace spaces with underscores
        header_value = f"{entity_name}.{espo_field}"  # No C prefix needed
        custom_headers[header_key] = header_value
    
    # Add required Kobo Connect headers
    custom_headers['targeturl'] = espo_url
    custom_headers['targetkey'] = espo_api_key
    
    # Kobo REST service endpoint
    url = f"{kobo_url}/api/v2/assets/{asset_id}/hooks/"
    
    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json"
    }
    
    # REST service configuration for Kobo Connect
    service_name = f"Kobo Connect → EspoCRM ({entity_name})"
    
    payload = {
        "name": service_name,
        "endpoint": "https://kobo-connect.azurewebsites.net/kobo-to-espocrm",
        "active": True,
        "subset_fields": [],  # Send all fields
        "email_notification": True,  # Get notified if webhook fails
        "export_type": "json",
        "auth_level": "no_auth",  # Kobo Connect doesn't require auth
        "settings": {
            "custom_headers": custom_headers
        },
        "payload_template": ""  # Use default
    }
    
    print(f"\n{'='*80}")
    print(f"SETTING UP KOBO CONNECT REST SERVICE")
    print(f"{'='*80}")
    print(f"Form Asset ID: {asset_id}")
    print(f"Entity: {entity_name}")
    print(f"EspoCRM URL: {espo_url}")
    print(f"\nField Mapping (Custom HTTP Headers):")
    for kobo_field, header_value in custom_headers.items():
        if kobo_field not in ['targeturl', 'targetkey']:
            print(f"  {kobo_field} → {header_value}")
    print(f"\nKobo Connect Endpoint: {payload['endpoint']}")
    
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    
    service = response.json()
    
    print(f"\n✓ REST service created successfully!")
    print(f"  Service ID: {service.get('uid')}")
    print(f"  Service Name: {service.get('name')}")
    print(f"  Active: {service.get('active')}")
    print(f"{'='*80}\n")
    
    return service


def get_field_mapping_from_kobo_data(kobo_data, entity_name):
    """
    Generate field mapping from Kobo form data.
    
    Args:
        kobo_data: Kobo form data dict
        entity_name: Sanitized entity name
    
    Returns:
        dict mapping Kobo field names to EspoCRM field names
    """
    from validators import sanitize_field_name, SUPPORTED_FIELD_TYPES, UNSUPPORTED_FIELD_TYPES
    
    field_mapping = {}
    survey_questions = kobo_data.get('content', {}).get('survey', [])
    
    for question in survey_questions:
        q_type = question.get('type', '')
        q_name = question.get('name', '')
        
        # Skip if no name
        if not q_name or not q_name.strip():
            continue
        
        # Skip unsupported types
        if q_type in UNSUPPORTED_FIELD_TYPES or q_type not in SUPPORTED_FIELD_TYPES:
            continue
        
        try:
            # Map Kobo field name to sanitized EspoCRM field name
            espo_field_name = sanitize_field_name(q_name)
            field_mapping[q_name] = espo_field_name
        except:
            continue
    
    # Always include the name field
    if 'name' not in field_mapping:
        field_mapping['name'] = 'name'
    
    return field_mapping


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 7:
        print("Usage: python kobo_connect_setup.py KOBO_URL API_TOKEN ASSET_ID ENTITY_NAME ESPO_URL ESPO_API_KEY")
        print("\nExample:")
        print("  python kobo_connect_setup.py https://kobo.ifrc.org YOUR_TOKEN anKBnYk7uAma9255UohxS9 CChadDemo http://20.56.35.22 your_api_key")
        sys.exit(1)
    
    kobo_url = sys.argv[1]
    api_token = sys.argv[2]
    asset_id = sys.argv[3]
    entity_name = sys.argv[4]
    espo_url = sys.argv[5]
    espo_api_key = sys.argv[6]
    
    # Example field mapping (in real use, this would be generated from the form)
    field_mapping = {
        'Name': 'name',
        'Date_of_Birth': 'dateOfBirth',
        'photo': 'photo',
        'income_source': 'incomeSource',
        'village': 'village'
    }
    
    try:
        service = setup_kobo_connect_rest_service(
            kobo_url,
            api_token,
            asset_id,
            entity_name,
            field_mapping,
            espo_url,
            espo_api_key
        )
        
        print("\n" + "="*80)
        print("SETUP COMPLETE!")
        print("="*80)
        print("\nYour Kobo form will now automatically send submissions to EspoCRM")
        print("via Kobo Connect middleware.")
        print(f"\nService ID: {service.get('uid')}")
        print("\nTo test:")
        print("1. Submit a form in Kobo")
        print("2. Check EspoCRM for the new record")
        print("3. Check Kobo REST Service logs for any errors")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()