import requests
import json
import os
from validators import ValidationError


class EspoAPIError(Exception):
    """Raised when EspoCRM API calls fail"""
    pass


class EspoAPI:
    """
    Handle direct API communication with EspoCRM instance.
    Uses basic auth with username/password to create entities, fields,
    and configure layouts/metadata.
    """
    
    def __init__(self, base_url, username, password):
        """
        Initialize EspoCRM API client.
        
        Args:
            base_url: EspoCRM instance URL (e.g., https://your-espo.com)
            username: Admin username
            password: Admin password
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def test_connection(self):
        """
        Test the connection and credentials by fetching user info.
        Returns True if successful, raises EspoAPIError otherwise.
        """
        try:
            response = self.session.get(f"{self.base_url}/api/v1/User")
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            raise EspoAPIError(f"Failed to connect to EspoCRM: {str(e)}")
    
    def create_entity(self, entity_data):
        """
        Create a new entity via EntityManager API.
        
        Args:
            entity_data: dict with entity definition
                {
                    "name": "MyEntity",
                    "labelSingular": "My Entity",
                    "labelPlural": "My Entities",
                    "type": "Base",
                    "stream": False,
                    "disabled": False,
                    "color": None,
                    "statusField": None
                }
        
        Returns:
            dict with created entity info
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/EntityManager/action/createEntity",
                json=entity_data
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise EspoAPIError(f"Failed to create entity: {str(e)}")
    
    def create_field(self, entity_name, field_data):
        """
        Create a field in an entity via FieldManager API.
        
        Args:
            entity_name: Name of the entity to add the field to
            field_data: dict with field definition
                {
                    "name": "myField",
                    "label": "My Field",
                    "type": "varchar",
                    "required": False,
                    "maxLength": 255,
                    ...other field-specific params
                }
        
        Returns:
            dict with created field info
        """
        try:
            # Base required fields for all types
            payload = {
                "required": False,
                "dynamicLogicVisible": None,
                "dynamicLogicRequired": None,
                "dynamicLogicReadOnly": None,
                "dynamicLogicInvalid": None,
                "dynamicLogicReadOnlySaved": None,
                "audited": False,
                "readOnly": False,
                "readOnlyAfterCreate": False,
                "inlineEditDisabled": False,
                "tooltipText": None,
                "tooltip": False
            }
            
            # Add type-specific defaults
            field_type = field_data.get('type', 'varchar')
            
            if field_type == 'varchar':
                payload['default'] = None
                payload['maxLength'] = field_data.get('maxLength', 255)
            elif field_type == 'int':
                payload['default'] = None
                payload['min'] = None
                payload['max'] = None
                payload['disableFormatting'] = False
            elif field_type == 'enum':
                payload['default'] = None
                payload['isSorted'] = False
                # options and style should come from field_data
            elif field_type == 'text':
                payload['default'] = None
            elif field_type == 'bool':
                payload['default'] = False
            elif field_type == 'date':
                payload['default'] = None
            elif field_type == 'datetime':
                payload['default'] = None
            elif field_type == 'attachment':
                # Attachment fields have minimal extra fields
                pass
            
            # Override/add with provided field data
            payload.update(field_data)
            
            # Use the correct endpoint format: /api/v1/Admin/fieldManager/{EntityName}
            response = self.session.post(
                f"{self.base_url}/api/v1/Admin/fieldManager/{entity_name}",
                json=payload
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Try to get detailed error message from response
            error_detail = ""
            try:
                error_json = e.response.json()
                error_detail = f" - {error_json.get('message', error_json)}"
            except:
                error_detail = f" - Status: {e.response.status_code}, Response: {e.response.text[:500]}"
            raise EspoAPIError(f"Failed to create field '{field_data.get('name')}': {str(e)}{error_detail}")
        except requests.exceptions.RequestException as e:
            raise EspoAPIError(f"Failed to create field '{field_data.get('name')}': {str(e)}")
    
    def set_layout(self, entity_name, layout_type, layout_data):
        """
        Set a specific layout for an entity.
        
        Args:
            entity_name: Name of the entity (e.g., "CTesting")
            layout_type: Type of layout ('detail', 'list', 'listSmall', etc.)
            layout_data: Layout configuration (list or dict depending on type)
        
        Returns:
            dict with update result
        """
        try:
            # Use the correct endpoint: /api/v1/{EntityName}/layout/{layoutType}
            response = self.session.put(
                f"{self.base_url}/api/v1/{entity_name}/layout/{layout_type}",
                json=layout_data
            )
            response.raise_for_status()
            return response.json() if response.text else {"success": True}
        except requests.exceptions.HTTPError as e:
            # Try to get detailed error message from response
            error_detail = ""
            try:
                error_json = e.response.json()
                error_detail = f" - {error_json.get('message', error_json)}"
            except:
                error_detail = f" - Status: {e.response.status_code}, Response: {e.response.text[:500]}"
            raise EspoAPIError(f"Failed to set {layout_type} layout: {str(e)}{error_detail}")
        except requests.exceptions.RequestException as e:
            raise EspoAPIError(f"Failed to set {layout_type} layout: {str(e)}")
    
    def clear_cache(self):
        """
        Clear EspoCRM cache.
        This is needed after creating/modifying entities.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/Admin/clearCache"
            )
            response.raise_for_status()
            return response.json() if response.text else {"success": True}
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not clear cache via API: {str(e)}")
            return None
    
    def upload_extension(self, zip_file_path):
        """
        Upload an extension package to EspoCRM.
        EspoCRM expects base64-encoded file data in JSON format.
        
        Args:
            zip_file_path: Path to the extension .zip file
        
        Returns:
            dict with upload result including extension ID
        """
        import base64
        
        try:
            zip_filename = os.path.basename(zip_file_path)
            
            print(f"  Uploading file: {zip_filename}")
            print(f"  File size: {os.path.getsize(zip_file_path)} bytes")
            
            # Read and base64 encode the file (like the browser does)
            with open(zip_file_path, 'rb') as f:
                file_content = f.read()
                base64_content = base64.b64encode(file_content).decode('utf-8')
            
            # Send as JSON with base64 data URL (exactly like browser)
            payload = {
                "data": f"data:application/x-zip-compressed;base64,{base64_content}"
            }
            
            print(f"  Sending as base64-encoded JSON (browser format)")
            print(f"  Base64 length: {len(base64_content)} chars")
            
            # Use regular session with JSON headers
            response = self.session.post(
                f"{self.base_url}/api/v1/Extension/action/upload",
                json=payload,
                timeout=120
            )
            
            print(f"  Response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"  Response body: {response.text[:1000]}")
            
            response.raise_for_status()
            result = response.json()
            print(f"  Upload successful!")
            print(f"  Extension ID: {result.get('id')}")
            return result
                
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_json = e.response.json()
                error_detail = f" - {error_json.get('message', error_json)}"
            except:
                error_detail = f" - Status: {e.response.status_code}, Response: {e.response.text[:500]}"
            raise EspoAPIError(f"Failed to upload extension: {str(e)}{error_detail}")
        except Exception as e:
            raise EspoAPIError(f"Failed to upload extension: {str(e)}")
    
    def install_extension(self, extension_id):
        """
        Install an uploaded extension.
        
        Args:
            extension_id: ID of the uploaded extension
        
        Returns:
            dict with install result
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/Extension/action/install",
                json={"id": extension_id}
            )
            response.raise_for_status()
            return response.json() if response.text else {"success": True}
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_json = e.response.json()
                error_detail = f" - {error_json.get('message', error_json)}"
            except:
                error_detail = f" - Status: {e.response.status_code}, Response: {e.response.text[:500]}"
            raise EspoAPIError(f"Failed to install extension: {str(e)}{error_detail}")
        except requests.exceptions.RequestException as e:
            raise EspoAPIError(f"Failed to install extension: {str(e)}")
    
    def uninstall_extension(self, extension_id):
        """
        Uninstall an extension.
        
        Args:
            extension_id: ID of the extension to uninstall
        
        Returns:
            dict with uninstall result
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/Extension/action/uninstall",
                json={"id": extension_id}
            )
            response.raise_for_status()
            return response.json() if response.text else {"success": True}
        except requests.exceptions.RequestException as e:
            raise EspoAPIError(f"Failed to uninstall extension: {str(e)}")
    
    def rebuild(self):
        """
        Trigger a rebuild of the EspoCRM metadata and database schema.
        This is typically needed after creating entities/fields.
        """
        try:
            # Try the Action/rebuild endpoint first
            response = self.session.post(
                f"{self.base_url}/api/v1/Action/rebuild"
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Try alternative endpoint
            try:
                response = self.session.post(
                    f"{self.base_url}/api/v1/Admin/rebuild"
                )
                response.raise_for_status()
                return response.json()
            except:
                # Rebuild might not be available via API in all EspoCRM versions
                # Log but don't fail
                print(f"Warning: Could not trigger rebuild via API: {str(e)}")
                print("  Please manually rebuild: Administration → Rebuild")
                return None


def deploy_entity_via_package(espo_url, username, password, entity_name, kobo_data):
    """
    Deploy entity to EspoCRM by creating a package and uploading it via Extension API.
    This is more reliable than direct API creation as it includes all necessary PHP files.
    
    Args:
        espo_url: EspoCRM instance URL
        username: Admin username
        password: Admin password
        entity_name: Name of the entity (WITHOUT C prefix)
        kobo_data: Full Kobo form data with survey questions
    
    Returns:
        dict with deployment result
    """
    import tempfile
    import os
    import zipfile
    from datetime import datetime
    
    print("\n" + "="*80)
    print("DEPLOYING VIA EXTENSION PACKAGE")
    print("="*80)
    
    api = EspoAPI(espo_url, username, password)
    
    # Test connection first
    print(f"\n[1] Testing connection to {espo_url}...")
    try:
        api.test_connection()
        print("✓ Connection successful")
    except EspoAPIError as e:
        print(f"✗ Connection failed: {str(e)}")
        raise ValidationError(f"Cannot connect to EspoCRM: {str(e)}")
    
    # Build the extension package
    print(f"\n[2] Building extension package for {entity_name}...")
    try:
        from extension_generator import build_entity_files
        
        # Get all the files for this entity
        entity_files = build_entity_files(kobo_data, entity_name)
        
        # Create manifest - use minimal format that EspoCRM accepts
        manifest = {
            "name": f"KoboImport{entity_name}",  # No spaces or dashes
            "version": "1.0.0",
            "acceptableVersions": [">=7.0.0"],
            "author": "Kobo Bridge",
            "description": "Entity created from Kobo form",
            "releaseDate": datetime.now().strftime("%Y-%m-%d")
        }
        
        # Create temporary zip file
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, f"{entity_name}_extension.zip")
        
        print(f"  Creating zip at: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add manifest
            zipf.writestr('manifest.json', json.dumps(manifest, indent=4))
            print(f"    Added: manifest.json")
            
            # Add all entity files
            for file_path, content in entity_files.items():
                zipf.writestr(file_path, content)
                print(f"    Added: {file_path}")
        
        # Verify the zip was created successfully
        if not os.path.exists(zip_path):
            raise Exception(f"Zip file was not created at {zip_path}")
        
        zip_size = os.path.getsize(zip_path)
        print(f"✓ Package created: {zip_path}")
        print(f"   Files in package: {len(entity_files) + 1}")
        print(f"   Package size: {zip_size} bytes")
        
        # Verify the zip can be read
        try:
            with zipfile.ZipFile(zip_path, 'r') as verify_zip:
                zip_contents = verify_zip.namelist()
                print(f"   Verified zip contents: {len(zip_contents)} files")
                print(f"   Files in package:")
                for item in sorted(zip_contents):
                    info = verify_zip.getinfo(item)
                    print(f"     - {item} ({info.file_size} bytes)")
                
                if 'manifest.json' not in zip_contents:
                    raise Exception("manifest.json not found in zip")
                
                # Show manifest contents
                manifest_content = verify_zip.read('manifest.json').decode('utf-8')
                print(f"\n   Manifest contents:")
                print(f"   {manifest_content}")
                
        except zipfile.BadZipFile as e:
            raise Exception(f"Created zip file is corrupted: {e}")
        
    except Exception as e:
        print(f"✗ Failed to build package: {str(e)}")
        raise ValidationError(f"Failed to build extension package: {str(e)}")
    
    # Upload the package
    print(f"\n[3] Uploading extension package...")
    
    # Save a copy for debugging
    debug_zip_path = f"C:/Users/jharrison/espo-kobo/debug_{entity_name}_extension.zip"
    try:
        import shutil
        shutil.copy2(zip_path, debug_zip_path)
        print(f"   Debug: Saved copy to {debug_zip_path}")
    except:
        pass
    
    try:
        upload_result = api.upload_extension(zip_path)
        extension_id = upload_result.get('id')
        print(f"✓ Package uploaded successfully")
        print(f"   Extension ID: {extension_id}")
        print(f"   Upload result: {json.dumps(upload_result, indent=2)}")
    except EspoAPIError as e:
        print(f"✗ Upload failed: {str(e)}")
        raise ValidationError(f"Failed to upload extension: {str(e)}")
    
    # Install the extension
    print(f"\n[4] Installing extension...")
    try:
        install_result = api.install_extension(extension_id)
        print(f"✓ Extension installed successfully")
        print(f"   Install result: {json.dumps(install_result, indent=2)}")
    except EspoAPIError as e:
        print(f"✗ Installation failed: {str(e)}")
        raise ValidationError(f"Failed to install extension: {str(e)}")
    
    # CRITICAL: Clear cache after installation
    print(f"\n[5] Clearing cache (required after installation)...")
    for i in range(3):  # Try up to 3 times
        cache_result = api.clear_cache()
        if cache_result:
            print("✓ Cache cleared")
            break
        else:
            print(f"  Attempt {i+1}/3 failed, retrying...")
            import time
            time.sleep(1)
    
    # CRITICAL: Rebuild after installation  
    print(f"\n[6] Rebuilding (required for routes to work)...")
    for i in range(3):  # Try up to 3 times
        rebuild_result = api.rebuild()
        if rebuild_result or rebuild_result is None:
            print("✓ Rebuild triggered")
            break
        else:
            print(f"  Attempt {i+1}/3 failed, retrying...")
            import time
            time.sleep(1)
    
    # Clean up temp file
    try:
        os.remove(zip_path)
        os.rmdir(temp_dir)
    except:
        pass
    
    print("\n" + "="*80)
    print("DEPLOYMENT COMPLETE - MANUAL STEP REQUIRED")
    print(f"Entity: C{entity_name}")
    print(f"Extension ID: {extension_id}")
    print("="*80)
    
    print("\n✓ Extension uploaded and installed successfully!")
    print("\n" + "!"*80)
    print("⚠️  CRITICAL: YOU MUST REBUILD NOW")
    print("!"*80)
    print("\nThe entity has been created but routes are not registered yet.")
    print("Without rebuilding, you'll get 405 errors when creating records.")
    print("\nPLEASE DO THIS NOW:")
    print("  1. Go to EspoCRM: Administration → Clear Cache → Click 'Clear Cache'")
    print("  2. Then: Administration → Rebuild → Click 'Rebuild'")
    print("  3. Wait 30-60 seconds for rebuild to complete")
    print("  4. Refresh your browser (Ctrl+F5)")
    print("  5. You can now create records!")
    print("\nThis is a normal EspoCRM requirement after installing extensions.")
    print("="*80 + "\n")
    
    return {
        'success': True,
        'entity_name': f"C{entity_name}",
        'extension_id': extension_id,
        'method': 'package',
        'message': f"Entity 'C{entity_name}' deployed successfully via extension package"
    }


def deploy_entity_to_espo(espo_url, username, password, entity_name, fields, labels=None, groups=None, survey_questions=None):
    """
    High-level function to deploy a complete entity to EspoCRM with layouts.
    
    Args:
        espo_url: EspoCRM instance URL
        username: Admin username
        password: Admin password
        entity_name: Name of the entity (e.g., "HouseholdSurvey" - WITHOUT the C prefix)
        fields: dict of field definitions (from extension_generator.map_kobo_to_espo_fields)
        labels: dict with 'singular' and 'plural' labels (optional)
        groups: list of group definitions for panel layout (optional)
        survey_questions: list of original Kobo questions with labels (optional)
    
    Returns:
        dict with deployment result and any warnings
    """
    print("\n" + "="*80)
    print("STARTING DEPLOYMENT TO ESPOCRM")
    print("="*80)
    
    # Import here to avoid circular imports
    from validators import sanitize_field_name
    
    api = EspoAPI(espo_url, username, password)
    
    # Test connection first
    print(f"\n[1] Testing connection to {espo_url}...")
    try:
        api.test_connection()
        print("✓ Connection successful")
    except EspoAPIError as e:
        print(f"✗ Connection failed: {str(e)}")
        raise ValidationError(f"Cannot connect to EspoCRM: {str(e)}")
    
    # Prepare entity data
    if labels is None:
        labels = {
            'singular': entity_name,
            'plural': f"{entity_name}s"
        }
    
    entity_data = {
        "name": entity_name,  # EspoCRM will add 'C' prefix automatically
        "labelSingular": labels.get('singular', entity_name),
        "labelPlural": labels.get('plural', f"{entity_name}s"),
        "type": "Base",
        "stream": False,
        "disabled": False,
        "color": None,
        "statusField": None
    }
    
    print(f"\n[2] Creating entity...")
    print(f"Entity name (without C): {entity_name}")
    print(f"Entity data being sent:")
    print(json.dumps(entity_data, indent=2))
    
    # Create the entity
    try:
        entity_result = api.create_entity(entity_data)
        # EspoCRM returns the actual entity name with C prefix
        actual_entity_name = entity_result.get('name', f"C{entity_name}")
        print(f"✓ Entity created successfully")
        print(f"Actual entity name (with C): {actual_entity_name}")
        print(f"Entity result:")
        print(json.dumps(entity_result, indent=2))
    except EspoAPIError as e:
        print(f"✗ Entity creation failed: {str(e)}")
        raise ValidationError(f"Failed to create entity: {str(e)}")
    
    # Create each field
    print(f"\n[3] Creating fields...")
    print(f"Total fields to create: {len(fields)}")
    print(f"Field names: {list(fields.keys())}")
    
    created_fields = []
    field_errors = []
    field_labels = {}
    
    # Build a mapping of field names to their original Kobo questions for labels
    question_map = {}
    if survey_questions:
        for question in survey_questions:
            q_name = question.get('name', '')
            q_label = question.get('label', q_name)
            q_type = question.get('type', '')
            
            try:
                field_name = sanitize_field_name(q_name)
                question_map[field_name] = {
                    'label': q_label if q_label and str(q_label) != 'nan' and q_label != q_name else field_name,
                    'choices': question.get('choices', []),
                    'type': q_type
                }
            except:
                continue
    
    for idx, (field_name, field_def) in enumerate(fields.items(), 1):
        # Skip the 'name' field - it's auto-created by EspoCRM
        if field_name == 'name':
            print(f"\n  [{idx}/{len(fields)}] Skipping 'name' field (auto-created by EspoCRM)")
            continue
        
        print(f"\n  [{idx}/{len(fields)}] Creating field: {field_name}")
        
        # Get label from original Kobo question if available
        if question_map and field_name in question_map:
            kobo_question = question_map[field_name]
            label = kobo_question.get('label', field_name.replace('_', ' ').title())
            choices = kobo_question.get('choices', [])
        else:
            # Fallback to field definition or generated label
            label = field_def.get('label', field_name.replace('_', ' ').title())
            choices = []
        
        field_labels[field_name] = label
        
        # Get choices with labels for enum/multiEnum fields
        choice_labels = {}
        if choices:
            for choice in choices:
                choice_name = choice.get('name', '')
                choice_label = choice.get('label', choice_name)
                if choice_label and str(choice_label) != 'nan':
                    choice_labels[choice_name] = choice_label
        
        # Prepare field data for API
        field_data = {
            "name": field_name,
            "label": label,
            **{k: v for k, v in field_def.items() if k not in ['label', 'isCustom', 'audited']}
        }
        
        # For enum fields, add translatedOptions if we have choice labels
        if field_def.get('type') in ['enum', 'multiEnum'] and choice_labels:
            # Store choice labels for later - EspoCRM uses translatedOptions
            field_data['translatedOptions'] = choice_labels
        
        print(f"    Field definition from Kobo:")
        print(f"    {json.dumps(field_def, indent=6)}")
        print(f"    Label: {label}")
        if choice_labels:
            print(f"    Choice labels: {choice_labels}")
        print(f"    Field data being sent to EspoCRM:")
        print(f"    {json.dumps(field_data, indent=6)}")
        
        try:
            field_result = api.create_field(actual_entity_name, field_data)
            created_fields.append(field_name)
            print(f"    ✓ Field created successfully")
            print(f"    Response: {json.dumps(field_result, indent=6)}")
        except EspoAPIError as e:
            error_msg = f"{field_name}: {str(e)}"
            field_errors.append(error_msg)
            print(f"    ✗ Field creation failed: {str(e)}")
    
    print(f"\n[4] Field creation summary:")
    print(f"  Created: {len(created_fields)} fields")
    print(f"  Failed: {len(field_errors)} fields")
    if field_errors:
        print(f"  Errors:")
        for error in field_errors:
            print(f"    - {error}")
    
    # Set up layouts if groups provided
    if groups:
        print(f"\n[5] Setting up layouts...")
        print(f"Groups provided: {len(groups)}")
        print(f"Group structure:")
        print(json.dumps(groups, indent=2))
        
        try:
            from extension_generator import generate_detail_layout, generate_list_layout
            
            # Generate layouts - groups IS the panels structure
            detail_layout = generate_detail_layout(groups)
            list_layout = generate_list_layout(groups)  # Pass groups (panels), not fields
            
            print(f"Detail layout generated:")
            print(json.dumps(detail_layout, indent=2))
            print(f"List layout generated:")
            print(json.dumps(list_layout, indent=2))
            
            # Set detail layout
            print(f"Setting detail layout...")
            api.set_layout(actual_entity_name, 'detail', detail_layout)
            print(f"✓ Detail layout set")
            
            # Set list layout
            print(f"Setting list layout...")
            api.set_layout(actual_entity_name, 'list', list_layout)
            print(f"✓ List layout set")
            
            # Set listSmall (same as list but fewer columns)
            list_small = list_layout[:4]  # Just take first 4 columns
            print(f"Setting listSmall layout...")
            api.set_layout(actual_entity_name, 'listSmall', list_small)
            print(f"✓ ListSmall layout set")
            
        except Exception as e:
            error_msg = f"Layout generation: {str(e)}"
            field_errors.append(error_msg)
            print(f"✗ Layout setup failed: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n[5] No groups provided, skipping layout setup")
    
    # Update i18n labels
    # TODO: i18n API returns 405 Method Not Allowed - need to find correct endpoint
    print(f"\n[6] Skipping i18n update (API endpoint not available)")
    print(f"Note: Entity and field labels will use default formatting")
    
    # Commented out until we find the correct i18n endpoint
    # print(f"\n[6] Updating i18n labels...")
    # try:
    #     i18n_updates = {
    #         "Global": {
    #             "scopeNames": {
    #                 actual_entity_name: labels.get('singular', entity_name)
    #             },
    #             "scopeNamesPlural": {
    #                 actual_entity_name: labels.get('plural', f"{entity_name}s")
    #             }
    #         },
    #         actual_entity_name: {
    #             "fields": field_labels
    #         }
    #     }
    #     print(f"i18n updates being sent:")
    #     print(json.dumps(i18n_updates, indent=2))
    #     
    #     api.update_i18n(i18n_updates)
    #     print(f"✓ i18n labels updated")
    # except EspoAPIError as e:
    #     error_msg = f"i18n update: {str(e)}"
    #     field_errors.append(error_msg)
    #     print(f"✗ i18n update failed: {str(e)}")
    
    # Attempt rebuild
    print(f"\n[7] Clearing cache and rebuilding...")
    
    # Clear cache first
    cache_result = api.clear_cache()
    if cache_result:
        print("✓ Cache cleared")
    
    # Then rebuild
    api.rebuild()
    
    print("\n" + "="*80)
    print("DEPLOYMENT COMPLETE")
    print(f"Entity: {actual_entity_name}")
    print(f"Fields created: {len(created_fields)}")
    print(f"Errors: {len(field_errors)}")
    print("="*80)
    
    if len(created_fields) > 0:
        print("\n⚠ IMPORTANT POST-DEPLOYMENT STEPS:")
        print("1. Go to Administration → Clear Cache (if not done automatically)")
        print("2. Go to Administration → Rebuild (if not done automatically)")
        print("3. If you still get 405 errors when creating records:")
        print(f"   - Check Administration → Entity Manager → {actual_entity_name}")
        print("   - Ensure 'Disabled' is NOT checked")
        print("   - Click 'Edit' and verify all settings")
        print("\n")
    
    return {
        'success': True,
        'entity_name': actual_entity_name,
        'fields_created': len(created_fields),
        'field_errors': field_errors,
        'message': f"Entity '{actual_entity_name}' created with {len(created_fields)} fields"
    }