import zipfile
import json
import os
from validators import (
    sanitize_entity_name,
    sanitize_field_name,
    SUPPORTED_FIELD_TYPES,
    UNSUPPORTED_FIELD_TYPES,
    ValidationError
)

# Base path - this was previously wrong
BASE_PATH = "files/custom/Espo/Modules/Custom/Resources"

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

        # Skip unsupported types
        if q_type in UNSUPPORTED_FIELD_TYPES or q_type not in SUPPORTED_FIELD_TYPES:
            continue

        # Sanitize field name
        try:
            field_name = sanitize_field_name(q_name)
        except ValidationError:
            continue

        espo_type = SUPPORTED_FIELD_TYPES[q_type]
        field_def = {
            "type": espo_type,
            "isCustom": True,
            "audited": True
        }

        # Add options for select fields
        if q_type in ['select_one', 'select_multiple']:
            choices = question.get('choices', [])
            if choices:
                # Always include a blank option first for enums
                options = [''] + [choice['name'] for choice in choices]
                field_def['options'] = options
                field_def['style'] = {opt: None for opt in options}

            if q_type == 'select_multiple':
                field_def['storeArrayValues'] = True
                field_def['default'] = []

        # Required constraint
        if question.get('required', '').lower() in ['yes', 'true', '1']:
            field_def['required'] = True

        # varchar max length
        if espo_type == 'varchar':
            field_def['maxLength'] = 255

        fields[field_name] = field_def

    return fields


def generate_i18n(entity_name, survey_questions):
    """
    Generate en_US i18n file so field names display as readable labels in the UI
    """
    fields = {}
    options = {}

    # Always include the name field
    fields['name'] = 'Name'

    for question in survey_questions:
        q_type = question.get('type', '')
        q_name = question.get('name', '')
        q_label = question.get('label', q_name)

        if q_type in UNSUPPORTED_FIELD_TYPES or q_type not in SUPPORTED_FIELD_TYPES:
            continue

        try:
            field_name = sanitize_field_name(q_name)
        except ValidationError:
            continue

        # Use the Kobo label as the human-readable field name
        fields[field_name] = q_label if q_label and q_label != q_name else field_name

        # For select fields, map option keys to labels
        if q_type in ['select_one', 'select_multiple']:
            choices = question.get('choices', [])
            if choices:
                opt_map = {'': ''}
                for choice in choices:
                    opt_map[choice['name']] = choice.get('label', choice['name'])
                options[field_name] = opt_map

    return {
        "fields": fields,
        "links": {},
        "labels": {
            f"Create {entity_name}": f"Create {entity_name}"
        },
        "options": options
    }


def build_entity_files(kobo_data, entity_name):
    """
    Returns a dict of { zip_internal_path: content_string }
    for all files needed for one entity.
    The caller (app.py) writes these directly into the single output zip.
    """
    survey_questions = kobo_data.get('content', {}).get('survey', [])
    if not survey_questions:
        raise ValidationError("No survey questions found")

    espo_fields = map_kobo_to_espo_fields(survey_questions)

    scope_metadata = {
        "entity": True,
        "layouts": True,
        "tab": True,
        "acl": True,
        "customizable": True,
        "importable": True,
        "type": "Base",
        "module": "Custom",
        "object": True,
        "isCustom": True,
        "stream": False,
        "disabled": False
    }

    entity_defs = {
        "fields": espo_fields,
        "links": {
            "createdBy": {"type": "belongsTo", "entity": "User"},
            "modifiedBy": {"type": "belongsTo", "entity": "User"},
            "assignedUser": {"type": "belongsTo", "entity": "User"},
            "teams": {
                "type": "hasMany",
                "entity": "Team",
                "relationName": "entityTeam",
                "layoutRelationshipsDisabled": True
            }
        },
        "collection": {
            "orderBy": "name",
            "order": "asc",
            "textFilterFields": ["name"],
            "fullTextSearch": False,
            "countDisabled": False
        },
        "indexes": {
            "name": {"columns": ["name", "deleted"]}
        }
    }

    client_defs = {
        "controller": "controllers/record",
        "iconClass": "fas fa-clipboard-list",
        "boolFilterList": ["onlyMy"],
        "kanbanViewMode": False,
        "color": "#3498db"
    }

    record_defs = {
        "duplicateWhereBuilderClassName": "Espo\\Classes\\DuplicateWhereBuilders\\General",
        "updateDuplicateCheck": False
    }

    controller_php = f"""<?php

namespace Espo\\Modules\\Custom\\Controllers;

class {entity_name} extends \\Espo\\Core\\Templates\\Controllers\\Base
{{}}
"""

    i18n_en_us = generate_i18n(entity_name, survey_questions)

    # Return all files as a flat dict - app.py writes these into the zip
    return {
        f"{BASE_PATH}/module.json":
            json.dumps({"order": 30}, indent=4),
        f"{BASE_PATH}/metadata/scopes/{entity_name}.json":
            json.dumps(scope_metadata, indent=4),
        f"{BASE_PATH}/metadata/entityDefs/{entity_name}.json":
            json.dumps(entity_defs, indent=4),
        f"{BASE_PATH}/metadata/clientDefs/{entity_name}.json":
            json.dumps(client_defs, indent=4),
        f"{BASE_PATH}/metadata/recordDefs/{entity_name}.json":
            json.dumps(record_defs, indent=4),
        f"files/custom/Espo/Modules/Custom/Controllers/{entity_name}.php":
            controller_php,
        f"{BASE_PATH}/i18n/en_US/{entity_name}.json":
            json.dumps(i18n_en_us, indent=4),
    }