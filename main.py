import functions_framework
from google.cloud import firestore
import google.generativeai as genai
import os
import json
import re
from geopy.geocoders import Nominatim

db = firestore.Client()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

geolocator = Nominatim(user_agent="national_health_surveillance")

@functions_framework.http
def log_symptoms(request):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}
    request_json = request.get_json(silent=True)
    
    if request_json and 'location' in request_json and 'symptoms' in request_json:
        symptoms = request_json.get('symptoms', [])
        roll_no = request_json.get('roll_no', 'Unknown')
        raw_location = request_json.get('location', '')
        
        # --- DATA NORMALIZATION ---
        if re.search('[a-zA-Z]', raw_location):
            try:
                geo_result = geolocator.geocode(raw_location)
                if not geo_result and "," in raw_location:
                    fallback_address = ",".join(raw_location.split(",")[-2:]).strip()
                    geo_result = geolocator.geocode(fallback_address)
                
                if geo_result:
                    request_json['location'] = f"{geo_result.latitude},{geo_result.longitude}"
                else:
                    print(f"Could not resolve address at all: {raw_location}")
                    request_json['location'] = "16.4880, 80.6756" 
            except Exception as e:
                print(f"GEOCODING ERROR: {str(e)}")
                request_json['location'] = "16.4880, 80.6756"
        
        ai_data = {
            "seriousness": "Completely Safe",
            "medication": "No medication required.",
            "doctor": "No visit necessary."
        }
        
        if "None" not in symptoms and symptoms:
            try:
                model = genai.GenerativeModel('gemini-3.6-flash')
                prompt = f"""You are an expert clinical triage AI. A patient has reported the following symptoms: {', '.join(symptoms)}. 
                Analyze these symptoms carefully to determine the risk level. 
                Provide a strict JSON response with exactly three keys:
                "seriousness": You MUST evaluate the severity and output exactly one of these five phrases: "Completely Safe", "Nearly Safe", "Moderately Serious", "Serious", or "Terribly Serious". 
                "medication": Provide a specific clinical recommendation, OTC action, or state "Immediate medical intervention required".
                "doctor": The specific specialist to consult (e.g., General Physician, Pulmonologist, etc., or "No visit necessary").
                Output strictly raw JSON only. Do not use markdown blocks."""
                
                response = model.generate_content(prompt)
                ai_data = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
            except Exception as e:
                print(f"GEMINI ERROR: {str(e)}")
                ai_data["medication"] = "AI Assessment unavailable at this time."

        request_json['ai_assessment'] = ai_data
        request_json['timestamp'] = firestore.SERVER_TIMESTAMP
        
        db.collection('surveillance_logs').add(request_json)
        
        return ({"status": "success", "ai_data": ai_data}, 200, headers)
    
    return ({'error': 'Invalid payload'}, 400, headers)
