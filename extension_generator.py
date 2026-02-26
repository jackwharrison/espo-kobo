import json
from validators import (
    sanitize_field_name,
    SUPPORTED_FIELD_TYPES,
    UNSUPPORTED_FIELD_TYPES,
    ValidationError
)

BASE_PATH = "files/custom/Espo/Modules/Custom/Resources"


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

def map_kobo_to_espo_fields(survey_questions):
    """
    Map Kobo survey questions to EspoCRM field definitions.
    Skips group markers and unsupported types.
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

        if q_type in UNSUPPORTED_FIELD_TYPES or q_type not in SUPPORTED_FIELD_TYPES:
            continue

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

        if q_type in ['select_one', 'select_multiple']:
            choices = question.get('choices', [])
            if choices:
                options = [''] + [choice['name'] for choice in choices]
                field_def['options'] = options
                field_def['style'] = {opt: None for opt in options}

            if q_type == 'select_multiple':
                field_def['storeArrayValues'] = True
                field_def['default'] = []

        if question.get('required', '').lower() in ['yes', 'true', '1']:
            field_def['required'] = True

        if espo_type == 'varchar':
            field_def['maxLength'] = 255

        fields[field_name] = field_def

    return fields


# ---------------------------------------------------------------------------
# Layout generation
# ---------------------------------------------------------------------------

def parse_groups(survey_questions):
    """
    Walk the survey questions and extract group structure.

    Returns a list of panels, each being:
      {
        'label': str,           # group label, or 'General' for ungrouped fields
        'fields': [str, ...],   # sanitized field names in order
        'is_repeat': bool       # True if this was a begin_repeat group
      }

    Rules:
    - Fields before any group go into a 'General' panel
    - Each top-level begin_group / begin_repeat starts a new panel
    - Nested groups are flattened into their parent panel
    - end_group / end_repeat closes the current group
    """
    panels = []
    current_panel = {'label': 'General', 'fields': [], 'is_repeat': False}
    group_stack = []
    depth = 0

    for question in survey_questions:
        q_type = question.get('type', '')
        q_name = question.get('name', '')
        q_label = question.get('label', q_name) or q_name

        if q_type == 'begin_group':
            depth += 1
            if depth == 1:
                if current_panel['fields']:
                    panels.append(current_panel)
                current_panel = {'label': q_label, 'fields': [], 'is_repeat': False}
                group_stack.append(current_panel)
            else:
                group_stack.append({'label': q_label, 'fields': [], 'is_repeat': False})

        elif q_type == 'end_group':
            if depth == 1:
                if current_panel['fields']:
                    panels.append(current_panel)
                if group_stack:
                    group_stack.pop()
                current_panel = {'label': 'General', 'fields': [], 'is_repeat': False}
            elif depth > 1:
                if group_stack:
                    group_stack.pop()
            depth = max(0, depth - 1)

        elif q_type == 'begin_repeat':
            depth += 1
            if depth == 1:
                if current_panel['fields']:
                    panels.append(current_panel)
                current_panel = {'label': q_label, 'fields': [], 'is_repeat': True}
                group_stack.append(current_panel)
            else:
                group_stack.append({'label': q_label, 'fields': [], 'is_repeat': True})

        elif q_type == 'end_repeat':
            if depth == 1:
                if current_panel['fields']:
                    panels.append(current_panel)
                if group_stack:
                    group_stack.pop()
                current_panel = {'label': 'General', 'fields': [], 'is_repeat': False}
            elif depth > 1:
                if group_stack:
                    group_stack.pop()
            depth = max(0, depth - 1)

        else:
            if q_type not in SUPPORTED_FIELD_TYPES:
                continue
            try:
                field_name = sanitize_field_name(q_name)
            except ValidationError:
                continue
            current_panel['fields'].append(field_name)

    # Catch any trailing fields not closed by a group
    if current_panel['fields']:
        panels.append(current_panel)

    # Remove empty panels
    panels = [p for p in panels if p['fields']]

    if not panels:
        panels = [{'label': 'General', 'fields': [], 'is_repeat': False}]

    return panels


def fields_to_rows(fields, columns=2):
    """
    Distribute a flat list of field names into rows of `columns` cells.
    Odd fields out get false as padding.
    """
    rows = []
    for i in range(0, len(fields), columns):
        chunk = fields[i:i + columns]
        row = [{"name": f} for f in chunk]
        while len(row) < columns:
            row.append(False)
        rows.append(row)
    return rows


def generate_detail_layout(panels):
    """
    Generate detail.json - array of panels, each with rows of fields.
    Kobo groups become EspoCRM panels.
    """
    layout = []

    for panel in panels:
        if not panel['fields']:
            continue

        rows = fields_to_rows(panel['fields'], columns=2)

        panel_def = {
            "rows": rows,
            "dynamicLogicVisible": None,
            "style": "default",
            "dynamicLogicStyled": None,
            "tabBreak": False,
            "hidden": False,
            "noteText": None,
            "customLabel": panel['label']
        }

        if panel.get('is_repeat'):
            panel_def['noteText'] = f"Note: '{panel['label']}' was a repeat group in Kobo and has been flattened."
            panel_def['style'] = "warning"

        layout.append(panel_def)

    return layout


def generate_list_layout(panels, max_fields=5):
    """
    Generate list.json - first N fields across all panels, first is clickable.
    """
    all_fields = []
    for panel in panels:
        all_fields.extend(panel['fields'])

    preview_fields = []
    if 'name' not in all_fields:
        preview_fields.append('name')

    for f in all_fields:
        if f not in preview_fields:
            preview_fields.append(f)
        if len(preview_fields) >= max_fields:
            break

    layout = []
    for i, field in enumerate(preview_fields):
        entry = {"name": field, "align": "left"}
        if i == 0:
            entry["link"] = True
        layout.append(entry)

    return layout


def generate_list_small_layout(panels, max_fields=3):
    return generate_list_layout(panels, max_fields=max_fields)


def generate_filters_layout(panels):
    """
    Generate filters.json - all fields available as search filters.
    """
    all_fields = ['name']
    for panel in panels:
        for f in panel['fields']:
            if f not in all_fields:
                all_fields.append(f)
    return all_fields


def generate_side_panels_layout():
    return {
        "_delimiter_": {"disabled": True},
        "default": {"index": 0},
        "activities": {"index": 1},
        "history": {"index": 2}
    }


def generate_bottom_panels_layout():
    return {
        "_delimiter_": {"disabled": True},
        "stream": {
            "dynamicLogicVisible": None,
            "style": "default",
            "sticked": False,
            "index": 0
        }
    }


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

def generate_i18n(entity_name, survey_questions, use_kobo_id_for_name=False):
    """
    Generate en_US i18n so field names display as readable labels in the UI.
    Uses Kobo question labels directly.
    
    Args:
        use_kobo_id_for_name: If True, label 'name' field as 'Kobo ID' instead of 'Name'
    """
    fields = {'name': 'Kobo ID' if use_kobo_id_for_name else 'Name'}
    options = {}

    for question in survey_questions:
        q_type = question.get('type', '')
        q_name = question.get('name', '')
        q_label = question.get('label', q_name) or q_name

        if q_type in UNSUPPORTED_FIELD_TYPES or q_type not in SUPPORTED_FIELD_TYPES:
            continue

        try:
            field_name = sanitize_field_name(q_name)
        except ValidationError:
            continue

        fields[field_name] = q_label if q_label != q_name else field_name

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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_entity_files(kobo_data, entity_name, use_kobo_id_for_name=False):
    """
    Returns a dict of { zip_internal_path: content_string }
    for all files needed for one entity.
    app.py writes these directly into the single output zip.
    
    Args:
        use_kobo_id_for_name: If True, label 'name' field as 'Kobo ID' (for REST service without name field)
    """
    survey_questions = kobo_data.get('content', {}).get('survey', [])
    if not survey_questions:
        raise ValidationError("No survey questions found")

    espo_fields = map_kobo_to_espo_fields(survey_questions)
    panels = parse_groups(survey_questions)

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

    i18n_en_us = generate_i18n(entity_name, survey_questions, use_kobo_id_for_name)

    layout_base = f"{BASE_PATH}/layouts/{entity_name}"

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

        f"{layout_base}/detail.json":
            json.dumps(generate_detail_layout(panels), indent=4),
        f"{layout_base}/list.json":
            json.dumps(generate_list_layout(panels), indent=4),
        f"{layout_base}/listSmall.json":
            json.dumps(generate_list_small_layout(panels), indent=4),
        f"{layout_base}/filters.json":
            json.dumps(generate_filters_layout(panels), indent=4),
        f"{layout_base}/sidePanelsDetail.json":
            json.dumps(generate_side_panels_layout(), indent=4),
        f"{layout_base}/bottomPanelsDetail.json":
            json.dumps(generate_bottom_panels_layout(), indent=4),
    }