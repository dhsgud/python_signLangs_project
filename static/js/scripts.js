function updateClock() {
    const now = new Date();
    const formattedTime = now.toLocaleString();
    document.getElementById('clock').innerText = formattedTime;
    setTimeout(updateClock, 1000);
}
function fetchFriends() {
    fetch('/api/friends')
        .then(response => response.json())
        .then(data => {
            const friendList = document.getElementById('friendList');
            friendList.innerHTML = '';
            data.friends.forEach(friend => {
                const div = document.createElement('div');
                div.innerText = friend.username;
                friendList.appendChild(div);
            });
        })
        .catch(error => console.error('Error:', error));
}
function addFriend(friendName) {
    fetch('/add_friend', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ friend_name: friendName })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            alert(data.message);
            fetchFriends();
        } else {
            alert(data.message);
        }
    })
    .catch(error => console.error('Error:', error));
}



document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const form = document.getElementById('messageForm');
    const messageInput = document.getElementById('messageInput');
    const messages = document.getElementById('messages');

    form.addEventListener('submit', event => {
        event.preventDefault();
        const message = messageInput.value;
        socket.emit('send_message', { username: 'User', message: message });
        messageInput.value = '';
    });

    socket.on('receive_message', data => {
        const messageElement = document.createElement('div');
        messageElement.textContent = `${data.username}: ${data.message}`;
        messages.appendChild(messageElement);
    });
});

document.getElementById('addFriendButton').addEventListener('click', function() {
        var friendName = document.getElementById('friendNameInput').value;
        addFriend(friendName);
    });

function startTranslation() {
    fetch('/start_translation')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert(data.message);
            } else {
                alert(data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('수화 번역 프로그램을 시작하는 중 오류가 발생했습니다.');
        });
}
