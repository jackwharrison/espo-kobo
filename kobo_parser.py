import pandas as pd
import requests
import json
from validators import ValidationError


def parse_xlsform(filepath):
    """
    Parse an XLSForm file and extract form structure.
    
    Args:
        filepath: Path to the XLS/XLSX file
    
    Returns:
        dict with form metadata and survey questions
        {
            'name': str,
            'content': {
                'survey': [list of questions]
            }
        }
    """
    try:
        # Read the survey sheet
        survey_df = pd.read_excel(filepath, sheet_name='survey')
        
        # Read choices sheet if exists
        try:
            choices_df = pd.read_excel(filepath, sheet_name='choices')
        except:
            choices_df = None
        
        # Extract form name from settings sheet or use default
        try:
            settings_df = pd.read_excel(filepath, sheet_name='settings')
            form_name = settings_df.iloc[0].get('form_title', 'KoboSurvey')
            if pd.isna(form_name):
                form_name = 'KoboSurvey'
        except:
            form_name = 'KoboSurvey'
        
        # Convert survey to list of questions
        questions = []
        for _, row in survey_df.iterrows():
            # Get basic question info
            q_type = str(row.get('type', '')).strip()
            q_name = str(row.get('name', '')).strip()
            
            # Skip questions with no name
            if not q_name or q_name == 'nan':
                continue
            
            # Handle multi-language labels (e.g., 'label::English (en)')
            # First try standard 'label' column
            q_label = row.get('label', q_name)
            
            # If label is NaN or empty, try language-specific columns
            if pd.isna(q_label) or str(q_label).strip() == '' or str(q_label) == 'nan':
                # Get all label columns
                label_columns = [col for col in survey_df.columns if col.startswith('label::')]
                
                # Prioritize English
                english_cols = [col for col in label_columns if 'english' in col.lower() or col.lower().endswith('(en)')]
                if english_cols:
                    potential_label = row.get(english_cols[0])
                    if not pd.isna(potential_label) and str(potential_label).strip() and str(potential_label) != 'nan':
                        q_label = potential_label
                
                # If no English label, use first available language
                if (pd.isna(q_label) or str(q_label).strip() == '' or str(q_label) == 'nan') and label_columns:
                    for label_col in label_columns:
                        potential_label = row.get(label_col)
                        if not pd.isna(potential_label) and str(potential_label).strip() and str(potential_label) != 'nan':
                            q_label = potential_label
                            break
                
                # If still no label found, use name
                if pd.isna(q_label) or str(q_label).strip() == '' or str(q_label) == 'nan':
                    q_label = q_name
            
            # Handle NaN labels
            if pd.isna(q_label):
                q_label = q_name
            else:
                q_label = str(q_label).strip()
            
            question = {
                'type': q_type,
                'name': q_name,
                'label': q_label,
            }
            
            # Add required field if present
            if pd.notna(row.get('required')):
                question['required'] = str(row.get('required')).lower()
            
            # Add constraint if present
            if pd.notna(row.get('constraint')):
                question['constraint'] = str(row.get('constraint'))
            
            # For select questions, extract choices
            if question['type'].startswith('select_'):
                # Parse "select_one list_name" or "select_multiple list_name"
                parts = question['type'].split()
                if len(parts) >= 2:
                    list_name = parts[1]
                    question['type'] = parts[0]  # select_one or select_multiple
                    
                    if choices_df is not None:
                        # Get choices for this list
                        choices_rows = choices_df[choices_df['list_name'] == list_name]
                        question['choices'] = []
                        
                        for _, choice_row in choices_rows.iterrows():
                            choice_name = str(choice_row.get('name', '')).strip()
                            choice_label = choice_row.get('label', choice_name)
                            
                            # Handle multi-language labels for choices
                            if pd.isna(choice_label) or str(choice_label).strip() == '' or str(choice_label) == 'nan':
                                # Get all label columns
                                label_columns = [col for col in choices_df.columns if col.startswith('label::')]
                                
                                # Prioritize English
                                english_cols = [col for col in label_columns if 'english' in col.lower() or col.lower().endswith('(en)')]
                                if english_cols:
                                    potential_label = choice_row.get(english_cols[0])
                                    if not pd.isna(potential_label) and str(potential_label).strip() and str(potential_label) != 'nan':
                                        choice_label = potential_label
                                
                                # If no English label, use first available language
                                if (pd.isna(choice_label) or str(choice_label).strip() == '' or str(choice_label) == 'nan') and label_columns:
                                    for label_col in label_columns:
                                        potential_label = choice_row.get(label_col)
                                        if not pd.isna(potential_label) and str(potential_label).strip() and str(potential_label) != 'nan':
                                            choice_label = potential_label
                                            break
                                
                                # If still no label, use name
                                if pd.isna(choice_label) or str(choice_label).strip() == '' or str(choice_label) == 'nan':
                                    choice_label = choice_name
                            
                            # Handle NaN labels
                            if pd.isna(choice_label):
                                choice_label = choice_name
                            else:
                                choice_label = str(choice_label).strip()
                            
                            question['choices'].append({
                                'name': choice_name,
                                'label': choice_label
                            })
            
            questions.append(question)
        
        return {
            'name': form_name,
            'content': {
                'survey': questions
            }
        }
    
    except Exception as e:
        raise ValidationError(f"Failed to parse XLS form: {str(e)}")


def fetch_kobo_form(asset_id, api_token, kobo_url='https://kobo.ifrc.org'):
    """
    Fetch form structure from KoboToolbox API.
    
    Args:
        asset_id: Kobo asset ID (from the form URL)
        api_token: Kobo API token
        kobo_url: Base URL for Kobo instance (default: https://kobo.ifrc.org)
    
    Returns:
        dict with form metadata and survey questions in same format as parse_xlsform
        {
            'name': str,
            'content': {
                'survey': [list of questions]
            }
        }
    """
    try:
        # Fetch asset from Kobo API
        url = f"{kobo_url}/api/v2/assets/{asset_id}/"
        headers = {"Authorization": f"Token {api_token}"}
        
        print(f"Fetching Kobo form from: {url}")
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        print(f"✓ Kobo form fetched successfully")
        print(f"  Form name: {data.get('name', 'Unknown')}")
        print(f"  Asset UID: {data.get('uid', 'Unknown')}")
        
        # Extract form content
        content = data.get('content', {})
        
        # The Kobo API returns the form in the same structure we need
        # but we need to ensure choices are properly formatted
        survey = content.get('survey', [])
        choices_list = content.get('choices', [])
        
        # Build a dict of choices by list_name for quick lookup
        choices_by_list = {}
        for choice in choices_list:
            list_name = choice.get('list_name', '')
            if list_name not in choices_by_list:
                choices_by_list[list_name] = []
            
            choice_data = {
                'name': choice.get('name', ''),
                'label': choice.get('label', [''])[0] if isinstance(choice.get('label'), list) else choice.get('label', '')
            }
            choices_by_list[list_name].append(choice_data)
        
        # Process survey questions
        processed_survey = []
        for question in survey:
            q_type = question.get('type', '')
            # Try multiple possible name fields
            q_name = question.get('name', '').strip()
            if not q_name:
                q_name = question.get('$autoname', '').strip()
            if not q_name:
                q_name = question.get('$kuid', '').strip()
            
            # Skip questions with no name
            if not q_name:
                print(f"  Warning: Skipping field with no name (type: {q_type})")
                print(f"  Raw question data: {json.dumps(question, indent=4)}")
                continue
            
            # Get label (might be a list with translations, take first)
            q_label = question.get('label', [q_name])
            if isinstance(q_label, list):
                q_label = q_label[0] if q_label else q_name
            
            processed_question = {
                'type': q_type,
                'name': q_name,
                'label': q_label,
            }
            
            # Add required if present
            if question.get('required'):
                processed_question['required'] = 'yes'
            
            # For select questions, attach choices
            if q_type in ['select_one', 'select_multiple']:
                select_from_list = question.get('select_from_list_name', '')
                if select_from_list and select_from_list in choices_by_list:
                    processed_question['choices'] = choices_by_list[select_from_list]
            
            processed_survey.append(processed_question)
        
        return {
            'name': data.get('name', 'KoboSurvey'),
            'content': {
                'survey': processed_survey
            }
        }
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise ValidationError("Invalid Kobo API token. Please check your token and try again.")
        elif e.response.status_code == 404:
            raise ValidationError(f"Kobo form not found. Asset ID '{asset_id}' does not exist or you don't have access to it.")
        else:
            raise ValidationError(f"Failed to fetch Kobo form: HTTP {e.response.status_code} - {str(e)}")
    
    except requests.exceptions.Timeout:
        raise ValidationError("Request to KoboToolbox timed out. Please try again.")
    
    except requests.exceptions.ConnectionError:
        raise ValidationError(f"Could not connect to KoboToolbox at {kobo_url}. Please check your internet connection.")
    
    except requests.exceptions.RequestException as e:
        raise ValidationError(f"Failed to fetch Kobo form: {str(e)}")
    
    except Exception as e:
        raise ValidationError(f"Error processing Kobo API response: {str(e)}")