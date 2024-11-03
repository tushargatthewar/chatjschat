from flask import Flask, render_template, redirect, request, url_for, flash, session, make_response
from flask_socketio import SocketIO, emit, join_room
from flask_session import Session
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
from urllib.parse import quote_plus
from pymongo import MongoClient


# Initialize Flask App and MongoDB connection
app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'mongodb'  # Store sessions in MongoDB
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'chat_'  # Prefix for session keys
Session(app)  # Initialize session
socketio = SocketIO(app)

# MongoDB Setup - Using MongoDB Atlas cluster URI
username = quote_plus("shubham")
password = quote_plus("shubham@123")
client = MongoClient(f"mongodb+srv://{username}:{password}@cluster0.ldylk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client['chat_ap']
users_collection = db['users']
rooms_collection = db['rooms']
messages_collection = db['messages']

# Home route redirects to login
@app.route('/')
def home():
    return redirect(url_for('login'))

# Login functionality
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users_collection.find_one({'username': username})
        
        if user and check_password_hash(user['password'], password):
            session_id = str(uuid.uuid4())  # Generate a unique session ID
            session['username'] = username
            session['session_id'] = session_id  # Store the session ID
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        
        # Check if user already exists
        if users_collection.find_one({'username': username}):
            flash('Username already exists', 'error')
        else:
            users_collection.insert_one({'username': username, 'password': hashed_password})
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'username' in session and 'session_id' in session:
        user_rooms = list(rooms_collection.find({'created_by': session['username']}))
        response = make_response(render_template('dashboard.html', username=session['username'], rooms=user_rooms, session_id=session['session_id']))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        return response
    return redirect(url_for('login'))

# Room creation
@app.route('/create_room', methods=['POST'])
def create_room():
    if 'username' in session:
        room_name = request.form.get('room_name')  # Use `.get()` to avoid KeyError
        if not room_name:
            flash("Room name is required.")
            return redirect(url_for('dashboard'))

        room_id = str(uuid.uuid4())
        rooms_collection.insert_one({'room_id': room_id, 'room_name': room_name, 'created_by': session['username']})
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Join room and view chat
@app.route('/join_room', methods=['POST'])
def join_room_post():
    room_id = request.form['room_id']
    return redirect(url_for('chat', room_id=room_id))

# Chat room
@app.route('/chat/<room_id>')
def chat(room_id):
    if 'username' in session:
        # Retrieve room details and messages
        room = rooms_collection.find_one({'room_id': room_id})
        messages = list(messages_collection.find({'room_id': room_id}))
        
        if room:
            # Pass session_id to chat.html
            return render_template(
                'chat.html',
                room_id=room_id,
                room_name=room.get('room_name'),
                username=session['username'],
                session_id=session['session_id'],
                messages=messages
            )
        else:
            flash('Room not found', 'error')
            return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Socket events for real-time messaging
@socketio.on('send_message')
def handle_message(data):
    room_id = data['room_id']
    message = data['message']
    username = session.get('username')
    
    # Store message in the database
    messages_collection.insert_one({'room_id': room_id, 'username': username, 'message': message})
    
    # Broadcast message to the room
    emit('receive_message', {'message': message, 'username': username}, room=room_id)

@socketio.on('join')
def on_join(data):
    room_id = data['room_id']
    join_room(room_id)
    
    # Emit initial messages for the room
    messages = list(messages_collection.find({'room_id': room_id}, {'_id': 0, 'username': 1, 'message': 1}))
    emit('initial_messages', {'messages': messages})

# Logout
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# Run the app
if __name__ == '__main__':
    socketio.run(app, debug=True)
