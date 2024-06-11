import sys
import cv2
import base64
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton
import socketio
import itertools
from collections import deque, Counter
import mediapipe as mp
from model import KeyPointClassifier, PointHistoryClassifier
from utils import CvFpsCalc
import csv
import time
import os

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class CameraApp(QWidget):
    def __init__(self, sio):
        super().__init__()
        self.sio = sio
        self.initUI()
        self.sio.on('hand_sign', self.display_gesture)
        self.setup_model()

    def initUI(self):
        self.setWindowTitle('Hand Gesture Recognition')
        self.setGeometry(100, 100, 800, 600)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.video_label = QLabel(self)
        self.layout.addWidget(self.video_label)

        self.gesture_label = QLabel(self)
        self.layout.addWidget(self.gesture_label)

        self.start_button = QPushButton('Start Camera', self)
        self.start_button.clicked.connect(self.startCamera)
        self.layout.addWidget(self.start_button)

        self.timer = QTimer()
        self.timer.timeout.connect(self.updateFrame)

        self.cap = None

    def setup_model(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )

        keypoint_classifier_tflite_path = resource_path('model/keypoint_classifier/keypoint_classifier.tflite')
        keypoint_classifier_label_path = resource_path('model/keypoint_classifier/keypoint_classifier_label.csv')
        point_history_classifier_label_path = resource_path('model/point_history_classifier/point_history_classifier_label.csv')

        self.keypoint_classifier = KeyPointClassifier(model_path=keypoint_classifier_tflite_path)
        self.point_history_classifier = PointHistoryClassifier()

        with open(keypoint_classifier_label_path, encoding='utf-8-sig') as f:
            self.keypoint_classifier_labels = [row[0] for row in csv.reader(f)]

        with open(point_history_classifier_label_path, encoding='utf-8-sig') as f:
            self.point_history_classifier_labels = [row[0] for row in csv.reader(f)]

        self.cvFpsCalc = CvFpsCalc(buffer_len=10)

        self.history_length = 16
        self.point_history = deque(maxlen=self.history_length)

        self.finger_gesture_history = deque(maxlen=self.history_length)

    def startCamera(self):
        self.cap = cv2.VideoCapture(0)
        self.timer.start(100)

    def updateFrame(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channel = frame.shape
            step = channel * width
            qImg = QImage(frame.data, width, height, step, QImage.Format_RGB888)
            self.video_label.setPixmap(QPixmap.fromImage(qImg))
            self.processFrame(frame)
            self.sendFrameToServer(frame)

    def processFrame(self, frame):
        results = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                landmark_list = self.calc_landmark_list(frame, hand_landmarks)
                pre_processed_landmarks = self.pre_process_landmarks(landmark_list)
                hand_sign_id = self.keypoint_classifier(pre_processed_landmarks)
                hand_sign_label = str(hand_sign_id)  # Convert to string for json mapping

                self.finger_gesture_history.append(hand_sign_id)
                most_common_fg_id = Counter(self.finger_gesture_history).most_common()

                self.gesture_label.setText(f'Hand Sign: {hand_sign_label}')
                self.sendHandSignToServer(hand_sign_label)
                time.sleep(1)  # 1초 딜레이

    def sendFrameToServer(self, frame):
        _, buffer = cv2.imencode('.jpg', frame)
        img_str = base64.b64encode(buffer).decode('utf-8')
        self.sio.emit('video_frame', img_str)

    def sendHandSignToServer(self, hand_sign_label):
        self.sio.emit('hand_sign', {'hand_sign': hand_sign_label})

    def display_gesture(self, data):
        self.gesture_label.setText(f'Hand Sign: {data["hand_sign"]}')

    def calc_landmark_list(self, image, landmarks):
        image_width, image_height = image.shape[1], image.shape[0]
        landmark_point = []

        for _, landmark in enumerate(landmarks.landmark):
            landmark_x = min(int(landmark.x * image_width), image_width - 1)
            landmark_y = min(int(landmark.y * image_height), image_height - 1)
            landmark_point.append([landmark_x, landmark_y])

        return landmark_point

    def pre_process_landmarks(self, landmark_list):
        temp_landmark_list = landmark_list.copy()

        base_x, base_y = 0, 0
        for index, landmark_point in enumerate(temp_landmark_list):
            if index == 0:
                base_x, base_y = landmark_point[0], landmark_point[1]

            temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
            temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

        temp_landmark_list = list(itertools.chain.from_iterable(temp_landmark_list))
        max_value = max(list(map(abs, temp_landmark_list)))
        temp_landmark_list = list(map(lambda x: x / max_value, temp_landmark_list))
        return temp_landmark_list

    def closeEvent(self, event):
        if self.cap:
            self.cap.release()
        event.accept()

if __name__ == '__main__':
    try:
        sio = socketio.Client()
        sio.connect('http://172.30.1.15:8002')
        app = QApplication(sys.argv)
        ex = CameraApp(sio)
        ex.show()
        sys.exit(app.exec_())
    except Exception as e:
        with open('error_log.txt', 'w') as f:
            f.write(str(e))
        print(f"An error occurred: {e}")
        input("Press Enter to exit...")
