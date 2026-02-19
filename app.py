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
            
            if not kobo_asset_id or not kobo_token:
                return jsonify({'error': 'Missing Kobo Asset ID or API Token'}), 400
            
            kobo_data = fetch_kobo_form(kobo_asset_id, kobo_token)
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
            
            if not kobo_asset_id or not kobo_token:
                return jsonify({'error': 'Missing Kobo Asset ID or API Token'}), 400
            
            kobo_data = fetch_kobo_form(kobo_asset_id, kobo_token)
            entity_name = kobo_data.get('name', 'KoboForm')
            kobo_forms.append({
                'data': kobo_data,
                'entity_name': entity_name
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
                
            except ValidationError as e:
                errors.append({'entity': form_info['entity_name'], 'error': str(e)})
        
        if not entity_names:
            return jsonify({
                'error': 'No extension could be generated',
                'details': errors
            }), 400
        
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