import pandas as pd
import requests
from validators import ValidationError

def parse_xlsform(filepath):
    """
    Parse an XLSForm file and extract form structure
    
    Returns: dict with form metadata and questions
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
        except:
            form_name = 'KoboSurvey'
        
        # Convert survey to list of questions
        questions = []
        for _, row in survey_df.iterrows():
            question = {
                'type': str(row.get('type', '')).strip(),
                'name': str(row.get('name', '')).strip(),
                'label': str(row.get('label', row.get('name', ''))).strip(),
            }
            
            # Add required field if present
            if pd.notna(row.get('required')):
                question['required'] = str(row.get('required')).lower()
            
            # Add constraint if present
            if pd.notna(row.get('constraint')):
                question['constraint'] = str(row.get('constraint'))
            
            # For select questions, extract choices
            if question['type'].startswith('select_'):
                list_name = question['type'].split()[-1] if ' ' in question['type'] else None
                question['type'] = question['type'].split()[0]  # select_one or select_multiple
                
                if list_name and choices_df is not None:
                    choices = choices_df[choices_df['list_name'] == list_name]
                    question['choices'] = [
                        {
                            'name': str(row['name']),
                            'label': str(row.get('label', row['name']))
                        }
                        for _, row in choices.iterrows()
                    ]
            
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
    Fetch form structure from KoboToolbox API
    
    Returns: dict with form metadata and questions
    """
    try:
        url = f"{kobo_url}/api/v2/assets/{asset_id}/"
        headers = {"Authorization": f"Token {api_token}"}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract relevant information
        return {
            'name': data.get('name', 'KoboSurvey'),
            'content': data.get('content', {})
        }
    
    except requests.exceptions.RequestException as e:
        raise ValidationError(f"Failed to fetch Kobo form: {str(e)}")
    except Exception as e:
        raise ValidationError(f"Error processing Kobo API response: {str(e)}")