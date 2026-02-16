import zipfile
import json
import os
from datetime import datetime
from validators import (
    sanitize_entity_name, sanitize_field_name,
    SUPPORTED_FIELD_TYPES, UNSUPPORTED_FIELD_TYPES,
    ValidationError
)

def map_kobo_to_espo_fields(survey_questions):
    """
    Map Kobo questions to EspoCRM field definitions
    """
    fields = {
        "name": {
            "type": "varchar",
            "required": True,
            "maxLength": 255
        }
    }
    
    for question in survey_questions:
        q_type = question.get('type', '')
        q_name = question.get('name', '')
        q_label = question.get('label', q_name)
        
        # Skip unsupported types
        if q_type in UNSUPPORTED_FIELD_TYPES or q_type not in SUPPORTED_FIELD_TYPES:
            continue
        
        # Sanitize field name
        try:
            field_name = sanitize_field_name(q_name)
        except ValidationError:
            continue  # Skip invalid field names
        
        # Map to EspoCRM field type
        espo_type = SUPPORTED_FIELD_TYPES[q_type]
        field_def = {"type": espo_type}
        
        # Add label
        if q_label and q_label != q_name:
            field_def['tooltip'] = q_label
        
        # Add options for select fields
        if q_type in ['select_one', 'select_multiple']:
            choices = question.get('choices', [])
            if choices:
                field_def['options'] = [choice['name'] for choice in choices]
                # Also store labels for translation
                field_def['translation'] = {
                    choice['name']: choice.get('label', choice['name'])
                    for choice in choices
                }
        
        # Add required constraint if exists
        if question.get('required', '').lower() in ['yes', 'true', '1']:
            field_def['required'] = True
        
        # Set max length for varchar fields
        if espo_type == 'varchar':
            field_def['maxLength'] = 255
        
        fields[field_name] = field_def
    
    return fields

def create_espo_extension(kobo_data, entity_name, output_dir):
    """
    Generate an EspoCRM extension package from Kobo form metadata
    
    Args:
        kobo_data: Dict containing Kobo form data
        entity_name: Name of the entity to create
        output_dir: Directory to save the extension package
    
    Returns:
        Path to the generated zip file
    """
    # Sanitize entity name
    sanitized_name = sanitize_entity_name(entity_name)
    
    # Parse survey questions
    survey_questions = kobo_data.get('content', {}).get('survey', [])
    if not survey_questions:
        raise ValidationError("No survey questions found")
    
    # Map fields
    espo_fields = map_kobo_to_espo_fields(survey_questions)
    
    # Create metadata structures
    scope_metadata = {
        "entity": True,
        "layouts": True,
        "tab": True,
        "acl": True,
        "customizable": True,
        "importable": True,
        "type": "Base",
        "module": "Custom",
        "object": True
    }
    
    entity_defs = {
        "fields": espo_fields,
        "links": {},
        "collection": {
            "orderBy": "createdAt",
            "order": "desc"
        },
        "indexes": {
            "name": {
                "columns": ["name", "deleted"]
            }
        }
    }
    
    client_defs = {
        "controller": "controllers/record",
        "iconClass": "fas fa-clipboard-list",
        "color": "#3498db",
        "kanbanViewMode": True,
        "quickCreate": True,
        "quickCreateOptions": {
            "defaultAttributes": {}
        }
    }
    
    # Create manifest
    manifest = {
        "name": f"Kobo Import - {sanitized_name}",
        "version": "1.0.0",
        "acceptableVersions": [">=7.0.0"],
        "author": "Kobo to EspoCRM Bridge",
        "description": f"Entity '{sanitized_name}' created from KoboToolbox form '{kobo_data.get('name', 'Unknown')}'",
        "skipBackup": True,
        "releaseDate": datetime.now().strftime("%Y-%m-%d")
    }
    
    # Create zip file
    zip_filename = f"{sanitized_name}_espo_extension.zip"
    zip_path = os.path.join(output_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add manifest
        zipf.writestr('manifest.json', json.dumps(manifest, indent=2))
        
        # Add metadata files
        base_path = f"files/custom/Espo/Custom/Resources/metadata"
        
        zipf.writestr(
            f"{base_path}/scopes/{sanitized_name}.json",
            json.dumps(scope_metadata, indent=2)
        )
        
        zipf.writestr(
            f"{base_path}/entityDefs/{sanitized_name}.json",
            json.dumps(entity_defs, indent=2)
        )
        
        zipf.writestr(
            f"{base_path}/clientDefs/{sanitized_name}.json",
            json.dumps(client_defs, indent=2)
        )
    
    return zip_path