from flask import Flask, request, jsonify, render_template, redirect, session, url_for, make_response
from datetime import datetime
import hashlib
import hmac
import json
import requests
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'your_secret_key'


ZOOM_CLIENT_ID = 'gJX1DO2EQee0U9mxQP7_FQ'
ZOOM_CLIENT_SECRET = 'DvxQtuRovhFY1cSV50eBhFu2xaRgbZA1'
ZOOM_REDIRECT_URI = 'https://attendx-r2pm.onrender.com/callback'
ZOOM_WEBHOOK_SECRET_TOKEN = 'fDsRUHSZTfyehR-qTm1I_A'  
attendance_data = {}

def get_zoom_authorization_url():
    return (
        'https://zoom.us/oauth/authorize'
        f'?response_type=code&client_id={ZOOM_CLIENT_ID}'
        f'&redirect_uri={ZOOM_REDIRECT_URI}'
    )

def get_zoom_token(authorization_code):
    url = 'https://zoom.us/oauth/token'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': ZOOM_REDIRECT_URI,
    }
    response = requests.post(url, headers=headers, data=data, auth=(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET))
    print("Zoom token response:", response.text)  # Log the full response text
    return response.json()

def create_zoom_meeting(access_token, topic, start_time, co_host_email, join_before_host):
    url = f'https://api.zoom.us/v2/users/me/meetings'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'topic': topic,
        'type': 2,
        'start_time': start_time,
        'settings': {
            'alternative_hosts': co_host_email,
            'join_before_host': join_before_host
        }
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.json()

def verify_signature(request):
    try:
        timestamp = request.headers.get('x-zm-request-timestamp', '')
        request_body = json.dumps(request.json, separators=(',', ':'))
        message = f"v0:{timestamp}:{request_body}"

        # Calculate the hash
        hash_for_verify = hmac.new(ZOOM_WEBHOOK_SECRET_TOKEN.encode(), message.encode(), hashlib.sha256).hexdigest()
        signature = f"v0={hash_for_verify}"

        received_signature = request.headers.get('x-zm-signature', '')
        print(f"Message to hash: {message}")
        print(f"Calculated signature: {signature}")
        print(f"Received signature: {received_signature}")

        return hmac.compare_digest(signature, received_signature)
    except Exception as e:
        print(f"Error in verify_signature: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print('Received data:', data)

    # Handling the URL validation event
    if data['event'] == 'endpoint.url_validation':
        plain_token = data['payload']['plainToken']
        
        # Create the encryptedToken by hashing the plainToken with the secret token
        hash_for_validate = hmac.new(
            ZOOM_WEBHOOK_SECRET_TOKEN.encode('utf-8'),
            msg=plain_token.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Respond with the plainToken and the encryptedToken
        return jsonify({'plainToken': plain_token, 'encryptedToken': hash_for_validate})

    # Verify Zoom Webhook signature for security purposes
    if not verify_signature(request):
        response = {'message': 'Unauthorized request to Zoom Webhook sample.'}
        return jsonify(response), 401

    try:
        event = data['event']
        meeting_id = data['payload']['object']['id']
        timestamp = datetime.fromtimestamp(data['event_ts'] / 1000.0)

        if meeting_id not in attendance_data:
            attendance_data[meeting_id] = {}

        # Participant joined the meeting
        if event == 'meeting.participant_joined' and 'participant' in data['payload']['object']:
            participant = data['payload']['object']['participant']
            user_name = participant['user_name']
            email = participant.get('email', '')  # In case email is not always present

            if user_name not in attendance_data[meeting_id]:
                # Initialize new participant entry with a join counter
                attendance_data[meeting_id][user_name] = {
                    'user_name': user_name,
                    'email': email,
                    'join_time': timestamp,
                    'leave_time': None,
                    'join_counter': 0
                }
            else:
                # Participant has rejoined, so increment the counter
                print(f"Participant rejoined: {user_name}")
                attendance_data[meeting_id][user_name]['join_counter'] += 1
                print(f"Join counter updated to: {attendance_data[meeting_id][user_name]['join_counter']}")

                # Update join time
                attendance_data[meeting_id][user_name]['join_time'] = timestamp
                attendance_data[meeting_id][user_name]['leave_time'] = None

        # Participant left the meeting
        elif event == 'meeting.participant_left' and 'participant' in data['payload']['object']:
            user_name = data['payload']['object']['participant']['user_name']

            if user_name in attendance_data[meeting_id]:
                # Update leave time when the participant leaves the meeting
                attendance_data[meeting_id][user_name]['leave_time'] = timestamp

        # Respond with success
        return jsonify({'status': 'success'})

    except KeyError as e:
        print(f"KeyError: Missing key {e} in the received data")
        return jsonify({'status': 'error', 'message': f'Missing key: {e}'}), 400

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/attendance/<meeting_id>', methods=['GET'])
def get_attendance(meeting_id):
    return jsonify(attendance_data.get(meeting_id, {}))

@app.route('/download_attendance/<meeting_id>')
def download_attendance(meeting_id):
    # Get the requested format (csv or pdf) from the query parameter
    format = request.args.get('format', 'csv')
    
    # Retrieve the attendance data for the given meeting_id
    attendance = attendance_data.get(meeting_id, {})
    
    # Extract the meeting topic and current date
    meeting_topic = attendance.get('topic', 'Meeting')
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # Create the filename using the meeting topic and date, replacing spaces with underscores
    filename = f"{meeting_topic}_{current_date}".replace(' ', '_').replace('/', '_')

    if format == 'csv':
        # CSV Generation
        csv_content = "Name,Email,Join Time,Leave Time,Join Counter\n"
        
        # Loop through participants and add their details to the CSV
        for participant in attendance.values():
            join_time = participant['join_time'].strftime('%Y-%m-%d %H:%M:%S')
            leave_time = participant['leave_time'].strftime('%Y-%m-%d %H:%M:%S') if participant['leave_time'] else 'Still in Meeting'
            join_counter = participant.get('join_counter', 0)
            csv_content += f"{participant['user_name']},{participant['email']},{join_time},{leave_time},{join_counter}\n"
        
        # Return as a CSV file with the updated filename
        response = make_response(csv_content)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    elif format == 'pdf':
        # PDF Generation with landscape orientation
        pdf = FPDF(orientation='L')  # Set orientation to landscape ('L')
        pdf.set_font("Arial", size=12)
        pdf.add_page()

        # Title
        pdf.cell(270, 10, txt="Attendance Report", ln=True, align='C')
        pdf.ln(10)

        # Column headers
        pdf.cell(60, 10, "Name", border=1)
        pdf.cell(60, 10, "Email", border=1)
        pdf.cell(60, 10, "Join Time", border=1)
        pdf.cell(60, 10, "Leave Time", border=1)
        pdf.cell(30, 10, "Join Count", border=1) 
        pdf.ln()

        # Participant rows
        for participant in attendance.values():
            join_time = participant['join_time'].strftime('%Y-%m-%d %H:%M:%S')
            leave_time = participant['leave_time'].strftime('%Y-%m-%d %H:%M:%S') if participant['leave_time'] else 'Still in Meeting'
            join_counter = participant.get('join_counter', 0)

            # Add rows with adjusted width for landscape layout
            pdf.cell(60, 10, participant['user_name'], border=1)
            pdf.cell(60, 10, participant['email'], border=1)
            pdf.cell(60, 10, join_time, border=1)
            pdf.cell(60, 10, leave_time, border=1)
            pdf.cell(30, 10, str(join_counter), border=1)  # Display join counter
            pdf.ln()

        # Output the PDF to a temporary location in memory with the updated filename
        response = make_response(pdf.output(dest='S').encode('latin1'))
        response.headers["Content-Disposition"] = f"attachment; filename={filename}.pdf"
        response.headers["Content-Type"] = "application/pdf"
        return response

@app.route('/')
def home():
    if 'zoom_access_token' not in session:
        print("No access token found, redirecting to Zoom authorization")
        return redirect(get_zoom_authorization_url())
    print("Access token found, user is logged in")
    return render_template('index.html')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    print("Authorization code received:", code)  # Log the received authorization code
    token_info = get_zoom_token(code)
    print("Token info received:", token_info)  # Log the token info
    if 'access_token' in token_info:
        session['zoom_access_token'] = token_info['access_token']
        return redirect(url_for('home'))
    else:
        return jsonify({'error': 'Failed to get access token'}), 400
    
@app.route('/create_meeting', methods=['POST'])
def create_meeting():
    if 'zoom_access_token' not in session:
        return redirect(get_zoom_authorization_url())
    data = request.json
    topic = data.get('topic')
    start_time = data.get('start_time')
    co_host_email = data.get('co_host_email')
    join_before_host = True
    access_token = session['zoom_access_token']
    meeting_info = create_zoom_meeting(access_token, topic, start_time, co_host_email, join_before_host)
    meeting_id = meeting_info.get('id')
    attendance_data[meeting_id] = {}
    return jsonify(meeting_info)

if __name__ == '__main__':
    app.run()