let autoUpdateInterval = null;
document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('meeting-form').addEventListener('submit', async function (event) {
        event.preventDefault();

        const form = event.target;
        const data = {
            topic: form.topic.value,
            start_time: form.start_time.value,
        };

        const spinner = document.getElementById('loading-spinner');
        spinner.style.display = 'inline';  // Show loading spinner

        try {
            const response = await fetch('/create_meeting', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            if (response.ok) {
                const result = await response.json();
                if (result.id) {
                    document.getElementById('meeting_id').value = result.id;
                    const meetingLink = `https://zoom.us/j/${result.id}`;
                    document.getElementById('meeting_link').innerHTML = `Meeting Link: <a href="${meetingLink}" target="_blank">${meetingLink}</a>`;
                    navigateTo('attendance');
                    openModal('Meeting created successfully! Meeting ID: ' + result.id);
                } else {
                    openModal('Error creating meeting');
                }
            } else {
                console.error('Error creating meeting:', response.statusText);
            }
        } catch (error) {
            console.error('Error creating meeting:', error);
            openModal('Error creating meeting');
        } finally {
            spinner.style.display = 'none';  // Hide loading spinner
        }
    });
});

function navigateTo(section) {
    document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.icon-container').forEach(icon => icon.classList.remove('active'));

    document.getElementById(section).classList.add('active');
    document.getElementById(section === 'meeting-setup' ? 'create-meeting-icon' : 'attendance-icon').classList.add('active');
}



function toggleAutoUpdate() {
    const autoUpdateEnabled = document.getElementById('auto-update-toggle').checked;
    const intervalSecs = parseInt(document.getElementById('update-interval').value);

    if (autoUpdateEnabled) {
        if (intervalSecs > 0) {
            autoUpdateInterval = setInterval(loadAttendance, intervalSecs * 1000);
            console.log(`Auto-update started with interval: ${intervalSecs} seconds.`);
        } else {
            alert('Please enter a valid interval.');
            document.getElementById('auto-update-toggle').checked = false;
        }
    } else {
        clearInterval(autoUpdateInterval);
        console.log('Auto-update stopped.');
    }
}

// Ensure to call toggleAutoUpdate on checkbox change
document.getElementById('auto-update-toggle').addEventListener('change', toggleAutoUpdate);

async function loadAttendance() {
    const meetingId = document.getElementById('meeting_id').value;
    if (!meetingId) {
        alert('Please enter a meeting ID');
        return;
    }

    try {
        const response = await fetch(`/attendance/${meetingId}`);
        if (response.ok) {
            const data = await response.json();
            const tbody = document.getElementById('attendance_table').getElementsByTagName('tbody')[0];
            tbody.innerHTML = '';
            for (const userId in data) {
                const participant = data[userId];
                const row = tbody.insertRow();
                row.insertCell(0).innerText = participant.user_name;
                row.insertCell(1).innerText = participant.email;
                row.insertCell(2).innerText = new Date(participant.join_time).toLocaleString();
                row.insertCell(3).innerText = participant.leave_time ? new Date(participant.leave_time).toLocaleString() : 'Still in Meeting';
                row.insertCell(4).innerText = participant.join_counter;
            }
        } else {
            console.error('Error loading attendance:', response.statusText);
        }
    } catch (error) {
        console.error('Error loading attendance:', error);
    }
}


function openModal(message) {
    document.getElementById('modal-message').innerText = message;
    document.getElementById('success-modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('success-modal').style.display = 'none';
}

async function downloadAttendance(format) {
    const meetingId = document.getElementById('meeting_id').value;

    // Request the download based on the selected format
    const response = await fetch(`/download_attendance/${meetingId}?format=${format}`);
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;

    // Set the filename based on the format
    if (format === 'pdf') {
        link.setAttribute('download', 'attendance.pdf');
    } else {
        link.setAttribute('download', 'attendance.csv');
    }

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    alert(`Downloading attendance as ${format}`)
}