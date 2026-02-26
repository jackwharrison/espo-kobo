from flask import Flask, request, send_file, render_template, jsonify
import tempfile
import os
import logging
import zipfile
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from kobo_parser import parse_xlsform, fetch_kobo_form
from extension_generator import build_entity_files
from validators import validate_package_safety, ValidationError
from espo_api import deploy_entity_to_espo, EspoAPIError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()



ALLOWED_EXTENSIONS = {'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')


# ============================================================================
# DIRECT DEPLOYMENT TO ESPOCRM
# ============================================================================

@app.route('/deploy-direct', methods=['POST'])
def deploy_direct():
    """
    Create entities directly in EspoCRM via API.
    Supports both XLS upload and Kobo API as data sources.
    """
    try:
        data = request.form
        espo_url = data.get('espoUrl', '').strip()
        espo_username = data.get('espoUsername', '').strip()
        espo_password = data.get('espoPassword', '').strip()
        data_source = data.get('dataSource', '').strip()
        
        if not all([espo_url, espo_username, espo_password, data_source]):
            return jsonify({'error': 'Missing required EspoCRM credentials or data source'}), 400
        
        # Get form data based on source
        kobo_forms = []
        kobo_url = None
        kobo_token = None
        kobo_asset_id = None
        
        if data_source == 'upload':
            # XLS file upload
            files = request.files.getlist('xlsforms')
            valid_files = [f for f in files if f.filename != '']
            
            if not valid_files:
                return jsonify({'error': 'No files uploaded'}), 400
            
            for file in valid_files:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                try:
                    kobo_data = parse_xlsform(filepath)
                    entity_name = os.path.splitext(filename)[0]
                    kobo_forms.append({
                        'data': kobo_data,
                        'entity_name': entity_name,
                        'source': filename
                    })
                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)
        
        elif data_source == 'kobo-api':
            # Kobo API
            kobo_asset_id = data.get('koboAssetId', '').strip()
            kobo_token = data.get('koboToken', '').strip()
            kobo_url = data.get('koboUrl', 'https://kobo.ifrc.org').strip()
            
            if not kobo_asset_id or not kobo_token:
                return jsonify({'error': 'Missing Kobo Asset ID or API Token'}), 400
            
            if not kobo_url:
                kobo_url = 'https://kobo.ifrc.org'
            
            kobo_data = fetch_kobo_form(kobo_asset_id, kobo_token, kobo_url)
            entity_name = kobo_data.get('name', 'KoboForm')
            kobo_forms.append({
                'data': kobo_data,
                'entity_name': entity_name,
                'source': f'Kobo Asset {kobo_asset_id}'
            })
        
        else:
            return jsonify({'error': 'Invalid data source'}), 400
        
        # Deploy each form to EspoCRM
        results = []
        errors = []
        
        print("\n" + "="*80)
        print(f"PROCESSING {len(kobo_forms)} FORM(S)")
        print("="*80)
        
        for form_idx, form_info in enumerate(kobo_forms, 1):
            print(f"\n{'='*80}")
            print(f"FORM {form_idx}/{len(kobo_forms)}: {form_info['source']}")
            print(f"{'='*80}")
            
            try:
                # Show raw Kobo data
                print(f"\nRaw Kobo form data:")
                print(f"  Name: {form_info['data'].get('name', 'N/A')}")
                print(f"  Entity name (base): {form_info['entity_name']}")
                
                survey_questions = form_info['data'].get('content', {}).get('survey', [])
                print(f"\n  Survey questions ({len(survey_questions)} items):")
                for q_idx, q in enumerate(survey_questions[:5], 1):  # Show first 5
                    print(f"    {q_idx}. {q.get('type', 'unknown')} - {q.get('name', 'no-name')} ({q.get('label', 'no-label')})")
                if len(survey_questions) > 5:
                    print(f"    ... and {len(survey_questions) - 5} more")
                
                # Validate
                print(f"\nValidating form...")
                validation_result = validate_package_safety(
                    form_info['data'],
                    form_info['entity_name']
                )
                
                entity_name = validation_result['sanitized_entity_name']
                print(f"  ✓ Validation passed")
                print(f"  Sanitized entity name: {entity_name}")
                if validation_result.get('warnings'):
                    print(f"  Warnings: {len(validation_result['warnings'])}")
                    for w in validation_result['warnings']:
                        print(f"    - {w}")
                
                # Deploy to EspoCRM using package method (more reliable)
                print(f"\nDeploying to EspoCRM via extension package...")
                
                from espo_api import deploy_entity_via_package
                
                deploy_result = deploy_entity_via_package(
                    espo_url,
                    espo_username,
                    espo_password,
                    entity_name,  # Without C prefix
                    form_info['data']  # Full Kobo data
                )
                
                print(f"\n✓ Deployment completed for {form_info['source']}")
                results.append({
                    'entity_name': deploy_result['entity_name'],
                    'source': form_info['source'],
                    'extension_id': deploy_result.get('extension_id'),
                    'method': 'package',
                    'warnings': validation_result.get('warnings', [])
                })
                
                # Setup Kobo Connect REST service if requested (only for Kobo API source)
                if data_source == 'kobo-api' and data.get('setupRestService') == 'true':
                    try:
                        print(f"\n[7] Setting up API user and Kobo Connect REST service...")
                        
                        # Step 1: Create API user and get key
                        from espo_api_user_setup import setup_api_user_for_entity
                        
                        api_user_result = setup_api_user_for_entity(
                            espo_url,
                            espo_username,
                            espo_password,
                            entity_name  # Without C prefix
                        )
                        
                        espo_api_key = api_user_result['api_key']
                        
                        # Step 2: Generate field mapping
                        from kobo_connect_setup import setup_kobo_connect_rest_service, get_field_mapping_from_kobo_data
                        
                        field_mapping = get_field_mapping_from_kobo_data(
                            form_info['data'],
                            entity_name
                        )
                        
                        # Step 3: Setup REST service in Kobo
                        rest_service = setup_kobo_connect_rest_service(
                            kobo_url=kobo_url,
                            api_token=kobo_token,
                            asset_id=kobo_asset_id,
                            entity_name=entity_name,  # No C prefix
                            field_mapping=field_mapping,
                            espo_url=espo_url,
                            espo_api_key=espo_api_key
                        )
                        
                        results[-1]['api_user'] = {
                            'username': api_user_result['username'],
                            'role_name': api_user_result['role_name']
                        }
                        results[-1]['rest_service_id'] = rest_service.get('uid')
                        results[-1]['rest_service_name'] = rest_service.get('name')
                        
                        print(f"✓ API user and REST service configured successfully")
                    
                    except Exception as e:
                        print(f"\n✗ Warning: Failed to setup REST service: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        results[-1]['rest_service_error'] = str(e)
                
            except (ValidationError, EspoAPIError) as e:
                print(f"\n✗ Deployment failed for {form_info['source']}: {str(e)}")
                errors.append({
                    'source': form_info['source'],
                    'error': str(e)
                })
        
        print(f"\n{'='*80}")
        print(f"DEPLOYMENT SUMMARY")
        print(f"{'='*80}")
        print(f"Successful: {len(results)}")
        print(f"Failed: {len(errors)}")
        print(f"{'='*80}\n")
        
        if not results:
            return jsonify({
                'error': 'No entities could be created',
                'details': errors
            }), 400
        
        return jsonify({
            'success': True,
            'results': results,
            'errors': errors
        })
    
    except Exception as e:
        logger.error(f"Deploy direct error: {str(e)}", exc_info=True)
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


# ============================================================================
# PACKAGE GENERATION (EXISTING FUNCTIONALITY)
# ============================================================================

@app.route('/generate-package', methods=['POST'])
def generate_package():
    """
    Generate extension package for manual installation.
    Supports both XLS upload and Kobo API as data sources.
    """
    try:
        data = request.form
        data_source = data.get('dataSource', '').strip()
        
        if not data_source:
            return jsonify({'error': 'Missing data source'}), 400
        
        # Get form data based on source
        kobo_forms = []
        
        if data_source == 'upload':
            files = request.files.getlist('xlsforms')
            valid_files = [f for f in files if f.filename != '']
            
            if not valid_files:
                return jsonify({'error': 'No files uploaded'}), 400
            
            for file in valid_files:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                try:
                    kobo_data = parse_xlsform(filepath)
                    entity_name = os.path.splitext(filename)[0]
                    kobo_forms.append({
                        'data': kobo_data,
                        'entity_name': entity_name
                    })
                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)
        
        elif data_source == 'kobo-api':
            kobo_asset_id = data.get('koboAssetId', '').strip()
            kobo_token = data.get('koboToken', '').strip()
            kobo_url = data.get('koboUrl', 'https://kobo.ifrc.org').strip()
            setup_rest_service = data.get('setupRestService', 'false') == 'true'
            
            if not kobo_asset_id or not kobo_token:
                return jsonify({'error': 'Missing Kobo Asset ID or API Token'}), 400
            
            if not kobo_url:
                kobo_url = 'https://kobo.ifrc.org'
            
            kobo_data = fetch_kobo_form(kobo_asset_id, kobo_token, kobo_url)
            entity_name = kobo_data.get('name', 'KoboForm')
            kobo_forms.append({
                'data': kobo_data,
                'entity_name': entity_name,
                'asset_id': kobo_asset_id,
                'kobo_url': kobo_url,
                'kobo_token': kobo_token,
                'setup_rest_service': setup_rest_service
            })
        
        else:
            return jsonify({'error': 'Invalid data source'}), 400
        
        # Build extension package
        all_entity_files = {}
        entity_names = []
        errors = []
        
        for form_info in kobo_forms:
            try:
                validation_result = validate_package_safety(
                    form_info['data'],
                    form_info['entity_name']
                )
                
                entity_name = validation_result['sanitized_entity_name']
                entity_files = build_entity_files(form_info['data'], entity_name)
                all_entity_files.update(entity_files)
                entity_names.append(entity_name)
                
                # Store sanitized entity name for REST service setup
                form_info['sanitized_entity_name'] = entity_name
                
            except ValidationError as e:
                errors.append({'entity': form_info['entity_name'], 'error': str(e)})
        
        if not entity_names:
            # All files failed
            error_details = "\n".join([f"• {e['entity']}: {e['error']}" for e in errors])
            return jsonify({
                'error': 'No valid entities could be generated from the uploaded files',
                'details': errors,
                'message': f"All {len(errors)} file(s) failed to process:\n{error_details}"
            }), 400
        
        # Log success and failures
        print(f"\n{'='*80}")
        print(f"PACKAGE GENERATION SUMMARY")
        print(f"{'='*80}")
        print(f"✓ Successful: {len(entity_names)} entity/entities")
        for name in entity_names:
            print(f"  - {name}")
        if errors:
            print(f"✗ Failed: {len(errors)} file(s)")
            for err in errors:
                print(f"  - {err['entity']}: {err['error']}")
        print(f"{'='*80}\n")
        
        # If there were failures, log a warning message
        if errors:
            logger.warning(f"Partial success: {len(entity_names)} succeeded, {len(errors)} failed")
            logger.warning(f"Failed entities: {', '.join([e['entity'] for e in errors])}")
        
        # Setup REST service if requested (only for Kobo API source)
        for form_info in kobo_forms:
            if form_info.get('setup_rest_service'):
                try:
                    from kobo_connect_setup import setup_kobo_connect_rest_service, get_field_mapping_from_kobo_data
                    
                    print(f"\n[REST SERVICE] Setting up Kobo Connect for {form_info['sanitized_entity_name']}...")
                    
                    # Generate field mapping
                    field_mapping = get_field_mapping_from_kobo_data(
                        form_info['data'],
                        form_info['sanitized_entity_name']
                    )
                    
                    # Check if _id is being mapped to name (means no name field exists)
                    using_kobo_id_for_name = '_id' in field_mapping and field_mapping['_id'] == 'name'
                    
                    # If using Kobo ID for name, rebuild the entity files with updated label
                    if using_kobo_id_for_name:
                        print(f"  No 'name' field found - using Kobo _id and labeling as 'Kobo ID'")
                        # Rebuild entity files with Kobo ID label
                        entity_files = build_entity_files(
                            form_info['data'],
                            form_info['sanitized_entity_name'],
                            use_kobo_id_for_name=True
                        )
                        # Update the zip with new files
                        all_entity_files.update(entity_files)
                    
                    # Setup REST service with placeholder values
                    rest_service = setup_kobo_connect_rest_service(
                        kobo_url=form_info['kobo_url'],
                        api_token=form_info['kobo_token'],
                        asset_id=form_info['asset_id'],
                        entity_name=form_info['sanitized_entity_name'],
                        field_mapping=field_mapping,
                        espo_url=None,  # Will use placeholder
                        espo_api_key=None  # Will use placeholder
                    )
                    
                    print(f"✓ REST service created with placeholders")
                    print(f"  Service ID: {rest_service.get('uid')}")
                    if using_kobo_id_for_name:
                        print(f"  Note: Kobo _id will populate the 'Kobo ID' field in EspoCRM")
                    print(f"  User must update targetkey and targeturl in Kobo")
                
                except Exception as e:
                    print(f"\n✗ Warning: Failed to setup REST service: {str(e)}")
                    import traceback
                    traceback.print_exc()
        
        
        # Create single zip with all entities
        temp_dir = tempfile.mkdtemp()
        zip_name = f"{entity_names[0]}_espo_extension.zip" if len(entity_names) == 1 else "espo_extensions_bundle.zip"
        zip_path = os.path.join(temp_dir, zip_name)
        
        manifest = {
            "name": f"Kobo Import - {', '.join(entity_names)}",
            "version": "1.0.0",
            "acceptableVersions": [">=7.0.0"],
            "releaseDate": datetime.now().strftime("%Y-%m-%d"),
            "author": "Kobo to EspoCRM Bridge",
            "description": f"Entities generated from KoboToolbox: {', '.join(entity_names)}"
        }
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr('manifest.json', json.dumps(manifest, indent=4))
            for file_path, content in all_entity_files.items():
                zipf.writestr(file_path, content)
        
        logger.info(f"Package created with {len(entity_names)} entity/entities")
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_name,
            mimetype='application/zip'
        )
    
    except Exception as e:
        logger.error(f"Generate package error: {str(e)}", exc_info=True)
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)