from flask import Flask, request, send_file, render_template, jsonify
import tempfile
import os
import logging
from werkzeug.utils import secure_filename
from kobo_parser import parse_xlsform, fetch_kobo_form
from extension_generator import create_espo_extension
from validators import validate_package_safety, ValidationError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

ALLOWED_EXTENSIONS = {'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-extension', methods=['POST'])
def generate_extension():
    try:
        # Validate that user provided exactly one input method
        has_file = 'xlsform' in request.files and request.files['xlsform'].filename != ''
        has_asset_id = request.form.get('assetId', '').strip() != ''
        
        if not has_file and not has_asset_id:
            return jsonify({
                'error': 'Please provide either an XLS form file OR a Kobo asset ID'
            }), 400
        
        if has_file and has_asset_id:
            return jsonify({
                'error': 'Please provide only ONE input method (either file OR asset ID, not both)'
            }), 400
        
        # Get Kobo form data based on input method
        if has_file:
            file = request.files['xlsform']
            
            # Validate file
            if not allowed_file(file.filename):
                return jsonify({
                    'error': 'Invalid file type. Please upload an .xls or .xlsx file'
                }), 400
            
            # Save temporarily and parse
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                kobo_data = parse_xlsform(filepath)
                logger.info(f"Parsed XLS form: {filename}")
            finally:
                # Clean up uploaded file
                if os.path.exists(filepath):
                    os.remove(filepath)
        
        else:  # has_asset_id
            asset_id = request.form.get('assetId', '').strip()
            api_token = request.form.get('apiToken', '').strip()
            
            if not api_token:
                return jsonify({
                    'error': 'Kobo API token is required when using asset ID'
                }), 400
            
            logger.info(f"Fetching Kobo form via API: {asset_id}")
            kobo_data = fetch_kobo_form(asset_id, api_token)
        
        # Get optional entity name or auto-generate
        entity_name = request.form.get('entityName', '').strip()
        if not entity_name:
            entity_name = kobo_data.get('name', 'KoboSurvey')
        
        # Validate package safety
        validation_result = validate_package_safety(kobo_data, entity_name)
        
        # Log warnings if any
        warnings = validation_result.get('warnings', [])
        if warnings:
            logger.warning(f"Package validation warnings: {warnings}")
        
        # Generate extension package
        temp_dir = tempfile.mkdtemp()
        zip_path = create_espo_extension(kobo_data, entity_name, temp_dir)
        
        logger.info(f"Extension package created: {zip_path}")
        
        # Send file to user
        safe_filename = secure_filename(f"{entity_name}_espo_extension.zip")
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='application/zip'
        )
    
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'An unexpected error occurred: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)