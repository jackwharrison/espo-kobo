"""
Test script to verify Kobo API connection

Usage:
    python test_kobo_api.py YOUR_ASSET_ID YOUR_API_TOKEN
"""

import sys
import json
from kobo_parser import fetch_kobo_form
from validators import ValidationError


def test_kobo_api(asset_id, api_token):
    """Test fetching a form from Kobo API"""
    
    print("="*80)
    print("TESTING KOBO API CONNECTION")
    print("="*80)
    print(f"\nAsset ID: {asset_id}")
    print(f"API Token: {api_token[:10]}..." if len(api_token) > 10 else f"API Token: {api_token}")
    
    try:
        # Fetch the form
        print("\nFetching form from Kobo...")
        form_data = fetch_kobo_form(asset_id, api_token)
        
        # Display results
        print("\n" + "="*80)
        print("✓ SUCCESS!")
        print("="*80)
        
        print(f"\nForm Name: {form_data.get('name')}")
        
        survey = form_data.get('content', {}).get('survey', [])
        print(f"Total Questions: {len(survey)}")
        
        print("\nFirst 5 questions:")
        for i, q in enumerate(survey[:5], 1):
            q_type = q.get('type', 'unknown')
            q_name = q.get('name', 'unnamed')
            q_label = q.get('label', q_name)
            print(f"  {i}. [{q_type}] {q_name}")
            print(f"     Label: {q_label}")
            
            # Show choices for select fields
            if 'choices' in q:
                print(f"     Choices: {len(q['choices'])} options")
                for choice in q['choices'][:3]:
                    print(f"       - {choice.get('name')} = {choice.get('label')}")
        
        if len(survey) > 5:
            print(f"  ... and {len(survey) - 5} more questions")
        
        print("\n" + "="*80)
        print("You can now use this Asset ID in the web interface!")
        print("="*80)
        
        return form_data
        
    except ValidationError as e:
        print("\n" + "="*80)
        print("✗ ERROR")
        print("="*80)
        print(f"\n{str(e)}")
        print("\nTroubleshooting:")
        print("1. Check your API token is correct")
        print("2. Verify the Asset ID from the form URL")
        print("3. Make sure you have access to this form")
        print("4. Go to: https://kf.kobotoolbox.org/#/account/security")
        return None
    
    except Exception as e:
        print("\n" + "="*80)
        print("✗ UNEXPECTED ERROR")
        print("="*80)
        print(f"\n{str(e)}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_kobo_api.py ASSET_ID API_TOKEN")
        print("\nExample:")
        print("  python test_kobo_api.py aBC123xyz your_api_token_here")
        print("\nGet your API token from:")
        print("  https://kf.kobotoolbox.org/#/account/security")
        print("\nFind Asset ID in your form URL:")
        print("  https://kf.kobotoolbox.org/#/forms/{ASSET_ID}/summary")
        sys.exit(1)
    
    asset_id = sys.argv[1]
    api_token = sys.argv[2]
    
    test_kobo_api(asset_id, api_token)