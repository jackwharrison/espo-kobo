from flask import Flask, request, send_file, render_template, jsonify
import tempfile
import os
import logging
import zipfile
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from kobo_parser import parse_xlsform
from extension_generator import build_entity_files
from validators import validate_package_safety, ValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64MB to allow multiple files
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
        files = request.files.getlist('xlsforms')

        # Validate at least one file was uploaded
        valid_files = [f for f in files if f.filename != '']
        if not valid_files:
            return jsonify({'error': 'Please upload at least one XLS form file'}), 400

        # Validate all files are the correct type
        invalid_files = [f.filename for f in valid_files if not allowed_file(f.filename)]
        if invalid_files:
            return jsonify({
                'error': f'Invalid file type(s): {", ".join(invalid_files)}. Please upload .xls or .xlsx files only'
            }), 400

        # Parse and validate each form, collecting all file contents into one dict
        all_entity_files = {}  # zip_path -> content
        entity_names = []
        errors = []

        for file in valid_files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                kobo_data = parse_xlsform(filepath)
                logger.info(f"Parsed XLS form: {filename}")

                entity_name = os.path.splitext(filename)[0]
                validation_result = validate_package_safety(kobo_data, entity_name)

                warnings = validation_result.get('warnings', [])
                if warnings:
                    logger.warning(f"{filename} warnings: {warnings}")

                # Returns a dict of { zip_internal_path: file_content }
                entity_files = build_entity_files(kobo_data, validation_result['sanitized_entity_name'])
                all_entity_files.update(entity_files)
                entity_names.append(validation_result['sanitized_entity_name'])

            except ValidationError as e:
                errors.append({'filename': filename, 'error': str(e)})
                logger.error(f"Validation error for {filename}: {str(e)}")

            except Exception as e:
                errors.append({'filename': filename, 'error': str(e)})
                logger.error(f"Error processing {filename}: {str(e)}", exc_info=True)

            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

        if not entity_names:
            return jsonify({
                'error': 'No extensions could be generated',
                'details': errors
            }), 400

        # Build one single zip containing all entity files + one shared manifest
        temp_dir = tempfile.mkdtemp()
        zip_name = f"{entity_names[0]}_espo_extension.zip" if len(entity_names) == 1 else "espo_extensions_bundle.zip"
        zip_path = os.path.join(temp_dir, zip_name)

        manifest = {
            "name": f"Kobo Import - {', '.join(entity_names)}",
            "version": "1.0.0",
            "acceptableVersions": [">=7.0.0"],
            "releaseDate": datetime.now().strftime("%Y-%m-%d"),
            "author": "Kobo to EspoCRM Bridge",
            "description": f"Entities generated from KoboToolbox forms: {', '.join(entity_names)}"
        }

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # One manifest at the top level
            zipf.writestr('manifest.json', json.dumps(manifest, indent=4))

            # All entity files written directly into the zip (no nesting of zips)
            for file_path, content in all_entity_files.items():
                zipf.writestr(file_path, content)

        logger.info(f"Single zip created with {len(entity_names)} entity/entities: {zip_path}")

        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_name,
            mimetype='application/zip'
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500


@app.route('/validate', methods=['POST'])
def validate_only():
    """Validate uploaded files and return a preview without generating"""
    try:
        files = request.files.getlist('xlsforms')
        valid_files = [f for f in files if f.filename != '']

        if not valid_files:
            return jsonify({'error': 'Please upload at least one XLS form file'}), 400

        results = []

        for file in valid_files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                kobo_data = parse_xlsform(filepath)
                entity_name = os.path.splitext(filename)[0]
                validation_result = validate_package_safety(kobo_data, entity_name)

                results.append({
                    'filename': filename,
                    'valid': True,
                    'entityName': validation_result['sanitized_entity_name'],
                    'fieldCount': validation_result['field_count'],
                    'warnings': validation_result.get('warnings', []),
                    'unsupportedFields': validation_result.get('unsupported_fields', [])
                })

            except ValidationError as e:
                results.append({
                    'filename': filename,
                    'valid': False,
                    'error': str(e)
                })

            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

        return jsonify({'results': results})

    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)