# check_metadata.py
import requests
import json
import sys # for flushing

print("Attempting to query metadata server for default service account info...")
sys.stdout.flush()
# Typical endpoint for default service account info, including the email
metadata_url_sa_info = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/?recursive=true"
headers = {"Metadata-Flavor": "Google"}

try:
    response = requests.get(metadata_url_sa_info, headers=headers, timeout=10) # Increased timeout slightly
    print(f"Status Code: {response.status_code}")
    sys.stdout.flush()
    print(f"Response Headers: {response.headers}")
    sys.stdout.flush()
    print(f"Response Text (first 500 chars): {response.text[:500]}")
    sys.stdout.flush()

    if response.ok:
        try:
            info_json = response.json()
            print("\nSuccessfully parsed response as JSON.")
            sys.stdout.flush()
            if "email" in info_json:
                print(f"Service Account Email from metadata: {info_json['email']}")
            else:
                print("\nWARNING: 'email' key NOT found in JSON response. Full JSON:")
                print(json.dumps(info_json, indent=2))
            sys.stdout.flush()
        except json.JSONDecodeError:
            print("\nCRITICAL: Response was NOT valid JSON. This is why the auth library is failing.")
            sys.stdout.flush()
    else:
        print("\nERROR: Metadata server returned a non-OK status code.")
        sys.stdout.flush()

except requests.exceptions.Timeout:
    print("\nERROR: Request to metadata server timed out. Check network or if metadata server is responsive.")
    sys.stdout.flush()
except requests.exceptions.RequestException as e:
    print(f"\nERROR: An error occurred while contacting the metadata server: {e}")
    sys.stdout.flush()

print("\nAttempting to query metadata server for project ID...")
sys.stdout.flush()
metadata_url_project_id = "http://metadata.google.internal/computeMetadata/v1/project/project-id"
try:
    response_project = requests.get(metadata_url_project_id, headers=headers, timeout=5)
    print(f"Project ID Status Code: {response_project.status_code}")
    sys.stdout.flush()
    print(f"Project ID Response Text: {response_project.text}")
    sys.stdout.flush()
except Exception as e:
    print(f"Error fetching project ID: {e}")
    sys.stdout.flush()

