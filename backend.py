import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import json

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['DEBUG'] = True  # 디버그 모드 활성화
socketio = SocketIO(app, async_mode='eventlet')

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

DATABASE = 'users2.db'

# 데이터베이스 연결 함수
def get_db_connection():
    logging.debug('Connecting to database...')
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        return None

# 데이터베이스 초기화 함수
def init_db():
    if not os.path.exists(DATABASE):
        logging.debug('Initializing database...')
        conn = get_db_connection()
        if conn is None:
            return
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER,
                friend_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(friend_id) REFERENCES users(id)
            )
        ''')

        cursor.execute('''  
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(receiver_id) REFERENCES users(id)
            )
        ''')

        conn.commit()
        conn.close()

# 데이터베이스 초기화
init_db()

@app.route('/')
def login():
    logging.debug('Rendering login page...')
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    if conn is None:
        return render_template('login.html', error='데이터베이스 연결 오류입니다.')

    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username=?', (username,))
    user = cursor.fetchone()

    if user and check_password_hash(user['password'], password):
        session['username'] = username
        logging.debug(f'User {username} logged in successfully.')
        return redirect(url_for('main'))
    else:
        logging.debug('Failed login attempt.')
        return render_template('login.html', error='사용자명 또는 비밀번호가 잘못되었습니다.')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_username = request.form['username']
        new_password = request.form['password']
        confirm_password = request.form['confirm_password']

        conn = get_db_connection()
        if conn is None:
            return render_template('register.html', error='데이터베이스 연결 오류입니다.')

        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username=?', (new_username,))
        existing_user = cursor.fetchone()

        if existing_user:
            logging.debug('Username already exists.')
            return render_template('register.html', error='이미 존재하는 사용자명입니다.')
        elif len(new_password) < 6:
            return render_template('register.html', error='비밀번호는 6자리 이상이어야 합니다.')
        elif new_password != confirm_password:
            return render_template('register.html', error='비밀번호가 일치하지 않습니다.')
        else:
            hashed_password = generate_password_hash(new_password)
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (new_username, hashed_password))
            conn.commit()
            logging.debug(f'User {new_username} registered successfully.')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/main')
def main():
    if 'username' not in session:
        return redirect(url_for('login'))

    return render_template('main.html', username=session['username'])

@app.route('/start_translation')
def start_translation():
    try:
        return jsonify({'status': 'success', 'message': '수화 번역 프로그램을 시작합니다.'})
    except Exception as e:
        logging.error(f"Error starting translation process: {e}")
        return jsonify({'status': 'error', 'message': f'수화 번역 프로그램을 시작하는 중 오류가 발생했습니다: {e}'})

@app.route('/api/hand_signs')
def api_hand_signs():
    try:
        with open('hand_sign.txt', 'r', encoding='utf-8') as file:
            hand_signs = file.readlines()
        return jsonify({'status': 'success', 'hand_signs': hand_signs})
    except Exception as e:
        logging.error(f"Error reading hand_sign.txt: {e}")
        return jsonify({'status': 'error', 'message': f'Error reading hand_sign.txt: {e}'})

@app.route('/friends')
def friends():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('friend.html')

@app.route('/api/friends')
def api_friends():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'message': '데이터베이스 연결 오류입니다.'}), 500

    cursor = conn.cursor()
    cursor.execute(
        'SELECT users.username FROM users JOIN friends ON users.id = friends.friend_id WHERE friends.user_id = (SELECT id FROM users WHERE username = ?)',
        (session['username'],))
    friends = cursor.fetchall()
    return jsonify({'friends': [dict(friend) for friend in friends]})

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if request.is_json:
        friend_name = request.json.get('friend_name')
        current_username = session['username']

        if friend_name == current_username:
            return jsonify({'status': 'error', 'message': '자신을 친구로 추가할 수 없습니다.'}), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({'status': 'error', 'message': '데이터베이스 연결 오류입니다.'}), 500

        cursor = conn.cursor()

        cursor.execute('SELECT id FROM users WHERE username=?', (friend_name,))
        friend = cursor.fetchone()
        if not friend:
            return jsonify({'status': 'error', 'message': '존재하지 않는 사용자입니다.'}), 404

        cursor.execute('''
            SELECT 1 FROM friends
            WHERE user_id=(SELECT id FROM users WHERE username=?)
            AND friend_id=?
        ''', (current_username, friend['id']))
        existing_friend = cursor.fetchone()

        if existing_friend:
            return jsonify({'status': 'error', 'message': '이미 친구로 추가된 사용자입니다.'}), 400

        cursor.execute('''
            INSERT INTO friends (user_id, friend_id)
            VALUES ((SELECT id FROM users WHERE username = ?), ?)
        ''', (current_username, friend['id']))
        conn.commit()

        logging.debug(f'Friend {friend_name} added successfully.')
        return jsonify({'status': 'success', 'message': '친구가 추가되었습니다.'})
    else:
        return jsonify({'status': 'error', 'message': '지원되지 않는 미디어 타입입니다.'}), 415

@app.route('/remove_friend', methods=['POST'])
def remove_friend():
    if request.is_json:
        friend_name = request.json.get('friend_name')
        current_username = session['username']

        conn = get_db_connection()
        if conn is None:
            return jsonify({'status': 'error', 'message': '데이터베이스 연결 오류입니다.'}), 500

        cursor = conn.cursor()

        cursor.execute('SELECT id FROM users WHERE username=?', (friend_name,))
        friend = cursor.fetchone()
        if not friend:
            return jsonify({'status': 'error', 'message': '존재하지 않는 사용자입니다.'}), 404

        cursor.execute('''
            DELETE FROM friends
            WHERE user_id=(SELECT id FROM users WHERE username=?)
            AND friend_id=?
        ''', (current_username, friend['id']))
        conn.commit()

        logging.debug(f'Friend {friend_name} removed successfully.')
        return jsonify({'status': 'success', 'message': '친구가 삭제되었습니다.'})
    else:
        return jsonify({'status': 'error', 'message': '지원되지 않는 미디어 타입입니다.'}), 415

@app.route('/messages')
def messages():
    if 'username' not in session:
        return redirect(url_for('login'))

    return render_template('messages.html')

@socketio.on('send_message')
def handle_message(data):
    sender_username = session.get('username')
    recipient_username = data['recipient']
    message_text = data['message']

    logging.debug(f'Sending message from {sender_username} to {recipient_username}: {message_text}')

    conn = get_db_connection()
    if conn is None:
        emit('receive_message', {'sender': 'System', 'message': '데이터베이스 연결 오류입니다.'}, room=sender_username)
        return

    cursor = conn.cursor()

    cursor.execute('SELECT id FROM users WHERE username=?', (sender_username,))
    sender = cursor.fetchone()
    cursor.execute('SELECT id FROM users WHERE username=?', (recipient_username,))
    recipient = cursor.fetchone()

    if sender and recipient:
        cursor.execute('''
            SELECT 1 FROM friends
            WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)
        ''', (sender['id'], recipient['id'], recipient['id'], sender['id']))
        are_friends = cursor.fetchone()

        if are_friends:
            cursor.execute('''
                INSERT INTO messages (sender_id, receiver_id, message)
                VALUES (?, ?, ?)
            ''', (sender['id'], recipient['id'], message_text))
            conn.commit()
            emit('receive_message', {'sender': sender_username, 'message': message_text}, room=recipient_username)
            emit('receive_message', {'sender': sender_username, 'message': message_text}, room=sender_username)
        else:
            emit('receive_message', {'sender': 'System', 'message': 'You can only send messages to friends.'},
                 room=sender_username)
    else:
        logging.error('Sender or recipient not found in the database.')

    conn.close()

@socketio.on('hand_sign')
def handle_hand_sign(data):
    hand_sign_text = data['hand_sign']

    # Load hand_sign_string.json and get corresponding text
    with open('hand_sign_string.json', 'r', encoding='utf-8') as f:
        hand_sign_dict = json.load(f)

    # Convert 0-based index to 1-based index for json mapping
    corresponding_text = hand_sign_dict.get(str(int(hand_sign_text) + 1), "Unknown sign")

    # Write to hand_sign.txt
    with open('hand_sign.txt', 'a', encoding='utf-8') as f:
        f.write(f'{corresponding_text}\n')

    emit('receive_hand_sign', {'hand_sign': corresponding_text}, broadcast=True)

@socketio.on('join')
def on_join(data):
    username = data['username']
    join_room(username)
    logging.debug(f'{username} joined the room.')

@app.route('/logout')
def logout():
    session.pop('username', None)
    logging.debug('User logged out.')
    return redirect(url_for('login'))

@socketio.on('leave')
def on_leave(data):
    username = data['username']
    leave_room(username)
    logging.debug(f'{username} left the room.')

if __name__ == '__main__':
    logging.debug('Starting Flask app...')
    socketio.run(app, host='172.30.1.15', port=8002, allow_unsafe_werkzeug=True)
