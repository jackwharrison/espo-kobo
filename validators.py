import re

class ValidationError(Exception):
    pass

# EspoCRM reserved field names that cannot be used
RESERVED_FIELD_NAMES = {
    'id', 'deleted', 'created_at', 'modified_at', 'created_by', 'modified_by',
    'created_by_id', 'modified_by_id', 'assigned_user', 'assigned_user_id',
    'teams', 'name_hash', 'type', 'parent_id', 'parent_type', 'parent_name',
    'is_followed', 'followers', 'version_number', 'entity_type'
}

# Reserved entity names
RESERVED_ENTITY_NAMES = {
    'User', 'Team', 'Role', 'Portal', 'Note', 'Attachment', 'Email',
    'EmailTemplate', 'Import', 'Webhook', 'Job', 'ScheduledJob',
    'AuthToken', 'UniqueId', 'Settings', 'FieldManager', 'Layout'
}

# Supported Kobo to EspoCRM field type mappings
SUPPORTED_FIELD_TYPES = {
    'text':              'varchar',
    'integer':           'int',
    'decimal':           'float',
    'date':              'date',
    'datetime':          'datetime',
    'time':              'varchar',
    'select_one':        'enum',
    'select_multiple':   'multiEnum',
    'note':              'text',
    'geopoint':          'varchar',
    'geotrace':          'text',
    'geoshape':          'text',
    'image':             'image',
    'audio':             'attachmentMultiple',
    'video':             'attachmentMultiple',
    'file':              'attachmentMultiple',
    'barcode':           'varchar',
    'acknowledge':       'bool',
    'calculate':         'varchar',
}

# Structural types - not data fields, used for layout grouping only
UNSUPPORTED_FIELD_TYPES = {
    'begin_group', 'end_group', 'begin_repeat', 'end_repeat',
    'begin_score', 'end_score', 'rank', 'score', 'xml-external'
}


def sanitize_entity_name(name):
    """
    Convert name to valid EspoCRM entity name: PascalCase
    E.g. "household survey" -> "HouseholdSurvey"
    Note: EspoCRM will automatically add 'C' prefix when creating via API.
    """
    # Remove special characters
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', name)

    # Convert to PascalCase
    words = cleaned.split()
    if not words:
        raise ValidationError("Entity name cannot be empty after sanitization")

    pascal_case = ''.join(word.capitalize() for word in words)

    # Ensure it starts with a letter
    if not pascal_case[0].isalpha():
        pascal_case = 'Entity' + pascal_case

    # Return WITHOUT C prefix - EspoCRM adds it automatically via API
    return pascal_case


def sanitize_field_name(name):
    """
    Convert name to valid EspoCRM field name (camelCase, alphanumeric only)
    """
    cleaned = re.sub(r'[^a-zA-Z0-9\s_]', '', name)
    parts = re.split(r'[\s_]+', cleaned)

    if not parts or not parts[0]:
        raise ValidationError(f"Field name '{name}' is invalid after sanitization")

    camel_case = parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])

    if not camel_case[0].isalpha():
        camel_case = 'field' + camel_case.capitalize()

    return camel_case


def check_reserved_words(field_names, entity_name):
    errors = []
    warnings = []

    if entity_name in RESERVED_ENTITY_NAMES:
        errors.append(f"Entity name '{entity_name}' is reserved by EspoCRM")

    for field in field_names:
        if field.lower() in RESERVED_FIELD_NAMES:
            errors.append(f"Field name '{field}' is reserved by EspoCRM")

    sql_keywords = {'select', 'where', 'from', 'insert', 'update', 'delete', 'drop', 'table'}
    for field in field_names:
        if field.lower() in sql_keywords:
            warnings.append(f"Field name '{field}' is an SQL keyword and may cause issues")

    return errors, warnings


def validate_field_count(field_count):
    if field_count == 0:
        raise ValidationError("Form must have at least one field")

    if field_count > 200:
        raise ValidationError(f"Too many fields ({field_count}). Maximum recommended is 200")

    warnings = []
    if field_count > 100:
        warnings.append(f"Large number of fields ({field_count}) may impact performance")

    return warnings


def check_malicious_input(data):
    dangerous_patterns = [
        r'<script', r'javascript:', r'onerror=', r'onclick=',
        r'\$\{', r'`', r'eval\(', r'exec\(',
        r'__import__', r'subprocess', r'os\.system'
    ]

    def scan_value(value, path=''):
        if isinstance(value, str):
            for pattern in dangerous_patterns:
                if re.search(pattern, value, re.IGNORECASE):
                    raise ValidationError(
                        f"Potentially malicious content detected at {path}: "
                        f"pattern '{pattern}' found"
                    )
        elif isinstance(value, dict):
            for k, v in value.items():
                scan_value(v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                scan_value(item, f"{path}[{i}]")

    scan_value(data)


def validate_package_safety(kobo_data, entity_name):
    """
    Main validation function - performs all safety checks.
    Returns dict with validation results and sanitized data.
    Raises ValidationError if validation fails.
    """
    errors = []
    warnings = []

    # 1. Check for malicious input
    try:
        check_malicious_input(kobo_data)
    except ValidationError as e:
        raise ValidationError(f"Security check failed: {str(e)}")

    # 2. Sanitize entity name
    try:
        sanitized_entity_name = sanitize_entity_name(entity_name)
    except ValidationError as e:
        raise ValidationError(f"Invalid entity name: {str(e)}")

    # 3. Parse and validate fields
    survey_questions = kobo_data.get('content', {}).get('survey', [])
    if not survey_questions:
        raise ValidationError("No survey questions found in Kobo form")

    field_names = []
    unsupported_fields = []

    for question in survey_questions:
        q_type = question.get('type', '')
        q_name = question.get('name', '')

        if q_type in UNSUPPORTED_FIELD_TYPES:
            continue  # structural elements, handled separately for layout

        if q_type not in SUPPORTED_FIELD_TYPES:
            unsupported_fields.append({
                'name': q_name,
                'type': q_type,
                'reason': 'Unsupported field type'
            })
            warnings.append(f"Field '{q_name}' of type '{q_type}' will be skipped")
            continue

        try:
            sanitized_name = sanitize_field_name(q_name)
            field_names.append(sanitized_name)
        except ValidationError as e:
            errors.append(f"Field '{q_name}': {str(e)}")

    # 4. Check field count
    field_count = len(field_names)
    try:
        count_warnings = validate_field_count(field_count)
        warnings.extend(count_warnings)
    except ValidationError:
        raise

    # 5. Check for reserved words
    reserved_errors, reserved_warnings = check_reserved_words(field_names, sanitized_entity_name)
    errors.extend(reserved_errors)
    warnings.extend(reserved_warnings)

    # 6. Check for duplicate field names
    seen = set()
    duplicates = set()
    for name in field_names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)

    if duplicates:
        errors.append(f"Duplicate field names found: {', '.join(duplicates)}")

    if errors:
        raise ValidationError('; '.join(errors))

    return {
        'valid': True,
        'sanitized_entity_name': sanitized_entity_name,
        'field_count': field_count,
        'warnings': warnings,
        'unsupported_fields': unsupported_fields
    }