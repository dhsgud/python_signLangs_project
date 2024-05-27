import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont
from datetime import datetime
from pjb import load_users, save_users
import csv
import copy
import argparse
import itertools
from collections import Counter
from collections import deque
import time
import cv2 as cv
import numpy as np
import mediapipe as mp
from utils import CvFpsCalc
from model import KeyPointClassifier
from model import PointHistoryClassifier
from PIL import Image, ImageTk

def login():
    username = entry_login_username.get()
    password = entry_login_password.get()

    users = load_users()

    if username in users and users[username] == password:
        messagebox.showinfo('로그인 성공', '로그인이 성공적으로 완료되었습니다.')
        open_main_window(username)
    else:
        messagebox.showerror('로그인 실패', '사용자명 또는 비밀번호가 잘못되었습니다.')

def submit_registration():
    username = entry_signup_username.get()
    password = entry_signup_password.get()
    confirm_password = entry_signup_confirm_password.get()

    users = load_users()

    if username in users:
        messagebox.showerror('회원가입 실패', '이미 존재하는 사용자명입니다.')
    elif password != confirm_password:
        messagebox.showerror('회원가입 실패', '비밀번호가 일치하지 않습니다.')
    else:
        users[username] = password
        save_users(users)
        messagebox.showinfo('회원가입 성공', '회원가입이 성공적으로 완료되었습니다.')
        signup_window.destroy()  # Close the signup window
        open_main_window(username)  # Open the main window

def open_main_window(username):
    # Destroy login window
    window.withdraw()

    # Create main window
    main_window = tk.Tk()
    main_window.title("Tsu - Main Window")
    main_window.geometry("800x600")  # Adjusted size to accommodate video

    # Create a frame for the header
    header_frame = tk.Frame(main_window)
    header_frame.pack(fill=tk.X, pady=10)

    # Username label (left-aligned)
    username_label = tk.Label(header_frame, text=username, font=("Helvetica", 12))
    username_label.pack(side=tk.LEFT, padx=10)

    # Current time label (centered)
    current_time_label = tk.Label(header_frame, text="", font=("Helvetica", 12))
    current_time_label.pack(side=tk.LEFT, anchor=tk.CENTER, expand=True)

    # Message button (right-aligned)
    message_button = tk.Button(header_frame, text="Message", font=("Helvetica", 12), command=lambda: open_message_window(username))
    message_button.pack(side=tk.RIGHT, padx=10)

    def update_time():
        current_time_label.config(text=datetime.now().strftime("%H:%M"))
        current_time_label.after(1000, update_time)

    update_time()

    # Frame for video
    video_frame = tk.Frame(main_window)
    video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Label for video
    video_label = tk.Label(video_frame)
    video_label.pack()

    # Video capture setup
    cap = cv.VideoCapture(0)

    def get_args():
        parser = argparse.ArgumentParser()

        parser.add_argument("--device", type=int, default=0)
        parser.add_argument("--width", help='cap width', type=int, default=960)
        parser.add_argument("--height", help='cap height', type=int, default=540)

        parser.add_argument('--use_static_image_mode', action='store_true')
        parser.add_argument("--min_detection_confidence",
                            help='min_detection_confidence',
                            type=float,
                            default=0.7)
        parser.add_argument("--min_tracking_confidence",
                            help='min_tracking_confidence',
                            type=float,
                            default=0.5)

        parser.add_argument("--start_id", help='start id', type=int, default=0)
        parser.add_argument("--duration", help='duration in seconds', type=int, default=10)

        args = parser.parse_args()

        return args

    def main():
        # 引数解析 #################################################################
        args = get_args()

        cap_device = args.device
        cap_width = args.width
        cap_height = args.height

        use_static_image_mode = args.use_static_image_mode
        min_detection_confidence = args.min_detection_confidence
        min_tracking_confidence = args.min_tracking_confidence

        start_id = args.start_id
        duration = args.duration

        use_brect = True

        # カメラ準備 ###############################################################
        cap = cv.VideoCapture(cap_device)
        cap.set(cv.CAP_PROP_FRAME_WIDTH, cap_width)
        cap.set(cv.CAP_PROP_FRAME_HEIGHT, cap_height)

        # モデルロード #############################################################
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=use_static_image_mode,
            max_num_hands=2,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        keypoint_classifier = KeyPointClassifier()
        point_history_classifier = PointHistoryClassifier()

        # ラベル読み込み ###########################################################
        with open(
                r'C:/Users/USER/PycharmProjects/python/model/keypoint_classifier/keypoint_classifier_label.csv',
                encoding='utf-8-sig') as f:
            keypoint_classifier_labels = [row[0] for row in csv.reader(f)]

        with open(
                r'C:/Users/USER/PycharmProjects/python/model/point_history_classifier/point_history_classifier_label.csv',
                encoding='utf-8-sig') as f:
            point_history_classifier_labels = [row[0] for row in csv.reader(f)]

        # FPS計測モジュール ########################################################
        cvFpsCalc = CvFpsCalc(buffer_len=10)

        # 座標履歴 #################################################################
        history_length = 16
        point_history = deque(maxlen=history_length)

        # フィンガージェスチャー履歴 ################################################
        finger_gesture_history = deque(maxlen=history_length)

        #  ########################################################################
        mode = 0
        current_id = start_id
        start_time = time.time()
        countdown = 0

        while True:
            fps = cvFpsCalc.get()

            # キー処理(ESC：終了) #################################################
            key = cv.waitKey(10)
            if key == 27:  # ESC
                break
            if key == ord('k'):
                mode = 1  # 손 좌표 데이터를 기록하는 모드
            if key == ord('h'):
                mode = 2  # 포인트 히스토리 데이터를 기록하는 모드

            # カメラキャプチャ #####################################################
            ret, image = cap.read()
            if not ret:
                break
            image = cv.flip(image, 1)  # ミラー表示
            debug_image = copy.deepcopy(image)

            # 検出実施 #############################################################
            image = cv.cvtColor(image, cv.COLOR_BGR2RGB)

            image.flags.writeable = False
            results = hands.process(image)
            image.flags.writeable = True

            #  ####################################################################
            if results.multi_hand_landmarks is not None:
                for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                    # 外接矩形の計算
                    brect = calc_bounding_rect(debug_image, hand_landmarks)
                    # ランドマークの計算
                    landmark_list = calc_landmark_list(debug_image, hand_landmarks)

                    # 相対座標・正規化座標への変換
                    pre_processed_landmark_list = pre_process_landmark(landmark_list)
                    pre_processed_point_history_list = pre_process_point_history(debug_image, point_history)
                    # 学習データ保存
                    if mode != 0:
                        logging_csv(current_id, mode, pre_processed_landmark_list, pre_processed_point_history_list)

                    # ハンドサイン分類
                    hand_sign_id = keypoint_classifier(pre_processed_landmark_list)
                    if hand_sign_id == 2:  # 指差しサイン
                        point_history.append(landmark_list[8])  # 人差指座標
                    else:
                        point_history.append([0, 0])

                    # フィンガージェスチャー分類
                    finger_gesture_id = 0
                    point_history_len = len(pre_processed_point_history_list)
                    if point_history_len == (history_length * 2):
                        finger_gesture_id = point_history_classifier(pre_processed_point_history_list)

                    # 直近検出の中で最多のジェスチャーIDを算出
                    finger_gesture_history.append(finger_gesture_id)
                    most_common_fg_id = Counter(finger_gesture_history).most_common()

                    # 描画
                    debug_image = draw_bounding_rect(use_brect, debug_image, brect)
                    debug_image = draw_landmarks(debug_image, landmark_list)
                    debug_image = draw_info_text(debug_image, brect, handedness,
                                                 keypoint_classifier_labels[hand_sign_id],
                                                 point_history_classifier_labels[most_common_fg_id[0][0]])
            else:
                point_history.append([0, 0])

            debug_image = draw_point_history(debug_image, point_history)
            debug_image = draw_info(debug_image, fps, mode, current_id, countdown)

            # 画面反映 #############################################################
            cv.imshow('Hand Gesture Recognition', debug_image)

            # 학습 시간 관리
            elapsed_time = time.time() - start_time
            if elapsed_time > duration:
                current_id += 1
                start_time = time.time()
                countdown = 0
            elif duration - elapsed_time <= 3:
                countdown = int(duration - elapsed_time)
            else:
                countdown = 0

        cap.release()
        cv.destroyAllWindows()

    def calc_bounding_rect(image, landmarks):
        image_width, image_height = image.shape[1], image.shape[0]

        landmark_array = np.empty((0, 2), int)

        for _, landmark in enumerate(landmarks.landmark):
            landmark_x = min(int(landmark.x * image_width), image_width - 1)
            landmark_y = min(int(landmark.y * image_height), image_height - 1)

            landmark_point = [np.array((landmark_x, landmark_y))]

            landmark_array = np.append(landmark_array, landmark_point, axis=0)

        x, y, w, h = cv.boundingRect(landmark_array)

        return [x, y, x + w, y + h]

    def calc_landmark_list(image, landmarks):
        image_width, image_height = image.shape[1], image.shape[0]

        landmark_point = []

        # キーポイント
        for _, landmark in enumerate(landmarks.landmark):
            landmark_x = min(int(landmark.x * image_width), image_width - 1)
            landmark_y = min(int(landmark.y * image_height), image_height - 1)
            # landmark_z = landmark.z

            landmark_point.append([landmark_x, landmark_y])

        return landmark_point

    def pre_process_landmark(landmark_list):
        temp_landmark_list = copy.deepcopy(landmark_list)

        # 相対座標に変換
        base_x, base_y = 0, 0
        for index, landmark_point in enumerate(temp_landmark_list):
            if index == 0:
                base_x, base_y = landmark_point[0], landmark_point[1]

            temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
            temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

        # 1次元リストに変換
        temp_landmark_list = list(itertools.chain.from_iterable(temp_landmark_list))

        # 正規化
        max_value = max(list(map(abs, temp_landmark_list)))

        def normalize_(n):
            return n / max_value

        temp_landmark_list = list(map(normalize_, temp_landmark_list))

        return temp_landmark_list

    def pre_process_point_history(image, point_history):
        image_width, image_height = image.shape[1], image.shape[0]

        temp_point_history = copy.deepcopy(point_history)

        # 相対座標に変換
        base_x, base_y = 0, 0
        for index, point in enumerate(temp_point_history):
            if index == 0:
                base_x, base_y = point[0], point[1]

            temp_point_history[index][0] = (temp_point_history[index][0] - base_x) / image_width
            temp_point_history[index][1] = (temp_point_history[index][1] - base_y) / image_height

        # 1次元リストに変換
        temp_point_history = list(itertools.chain.from_iterable(temp_point_history))

        return temp_point_history

    def logging_csv(current_id, mode, landmark_list, point_history_list):
        if mode == 0:
            return
        elif mode == 1:  # 손 좌표 데이터를 기록하는 모드
            csv_path = r'C:/Users/USER/PycharmProjects/python/model/keypoint_classifier/keypoint.csv'
            with open(csv_path, 'a', newline="") as f:
                writer = csv.writer(f)
                writer.writerow([current_id, *landmark_list])
        elif mode == 2:  # 포인트 히스토리 데이터를 기록하는 모드
            csv_path = r'C:/Users/USER/PycharmProjects/python/model/point_history_classifier/point_history.csv'
            with open(csv_path, 'a', newline="") as f:
                writer = csv.writer(f)
                writer.writerow([current_id, *point_history_list])

    def draw_landmarks(image, landmark_point):
        # 接続線
        if len(landmark_point) > 0:
            # 親指
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]), (255, 255, 255), 2)

            # 人差指
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]), (255, 255, 255), 2)

            # 中指
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]), (255, 255, 255), 2)

            # 薬指
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]), (255, 255, 255), 2)

            # 小指
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]), (255, 255, 255), 2)

            # 手の平
            cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]), (255, 255, 255), 2)
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]), (0, 0, 0), 6)
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]), (255, 255, 255), 2)

        # キーポイント
        for index, landmark in enumerate(landmark_point):
            if index in [0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19]:  # 小さな円
                cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
            else:  # 大きな円
                cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)

        return image

    def draw_bounding_rect(use_brect, image, brect):
        if use_brect:
            # 外接矩形
            cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[3]), (0, 0, 0), 1)

        return image

    def draw_info_text(image, brect, handedness, hand_sign_text, finger_gesture_text):
        cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[1] - 22), (0, 0, 0), -1)

        info_text = handedness.classification[0].label[0:]
        if hand_sign_text != "":
            info_text = info_text + ':' + hand_sign_text
        cv.putText(image, info_text, (brect[0] + 5, brect[1] - 4),
                   cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv.LINE_AA)

        if finger_gesture_text != "":
            cv.putText(image, "Finger Gesture:" + finger_gesture_text, (10, 60),
                       cv.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4, cv.LINE_AA)
            cv.putText(image, "Finger Gesture:" + finger_gesture_text, (10, 60),
                       cv.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv.LINE_AA)

        return image

    def draw_point_history(image, point_history):
        for index, point in enumerate(point_history):
            if point[0] != 0 and point[1] != 0:
                cv.circle(image, (point[0], point[1]), 1 + int(index / 2), (152, 251, 152), 2)

        return image

    def draw_info(image, fps, mode, current_id, countdown):
        cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4, cv.LINE_AA)
        cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv.LINE_AA)

        mode_string = ['Logging Key Point', 'Logging Point History']
        if 1 <= mode <= 2:
            cv.putText(image, "MODE:" + mode_string[mode - 1], (10, 90), cv.FONT_HERSHEY_SIMPLEX, 0.6,
                       (255, 255, 255), 1,
                       cv.LINE_AA)

        # 현재 학습 중인 ID 표시
        cv.putText(image, f"CURRENT ID: {current_id}", (10, 150), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                   cv.LINE_AA)

        # 카운트다운 표시
        if countdown > 0:
            cv.putText(image, f"Next ID in: {countdown}", (10, 210), cv.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 4,
                       cv.LINE_AA)
            cv.putText(image, f"Next ID in: {countdown}", (10, 210), cv.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255),
                       2, cv.LINE_AA)

        return image

    if __name__ == '__main__':
        main()
    # app.py의 절대 경로를 사용합니다.
    messagebox.showinfo('수화 번역', '수화 번역 프로그램이 시작되었습니다.')
    main_window.mainloop()

def open_message_window(username):
    message_window = tk.Tk()
    message_window.title("Tsu - Messages")
    message_window.geometry("400x600")

    # Create a frame for the message display and scrollbar
    message_frame = tk.Frame(message_window)
    message_frame.pack(pady=10, fill=tk.BOTH, expand=True)

    scrollbar = tk.Scrollbar(message_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Create a text widget to display messages
    message_display = tk.Text(message_frame, height=20, width=50, state=tk.DISABLED, bg="#f9f9f9", font=("Helvetica", 12), yscrollcommand=scrollbar.set)
    message_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=message_display.yview)

    # Create a frame for writing messages
    entry_frame = tk.Frame(message_window)
    entry_frame.pack(fill=tk.X, padx=10, pady=10)

    message_entry = tk.Entry(entry_frame, width=30, bg="#f9f9f9", font=("Helvetica", 12))
    message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

    def send_message():
        message = message_entry.get()
        if message:
            message_display.config(state=tk.NORMAL)
            message_display.insert(tk.END, f"{username}: {message}\n")
            message_display.config(state=tk.DISABLED)
            message_entry.delete(0, tk.END)
            message_display.yview(tk.END)

    send_button = tk.Button(entry_frame, text="Send", command=send_message, bg="#007bff", fg="#ffffff", font=("Helvetica", 12, "bold"))
    send_button.pack(side=tk.RIGHT, padx=10)

    message_window.mainloop()

def signup():
    username = entry_signup_username.get()
    password = entry_signup_password.get()
    confirm_password = entry_signup_confirm_password.get()

    users = load_users()

    if username in users:
        messagebox.showerror('회원가입 실패', '이미 존재하는 사용자명입니다.')
    elif password != confirm_password:
        messagebox.showerror('회원가입 실패', '비밀번호가 일치하지 않습니다.')
    else:
        users[username] = password
        save_users(users)
        messagebox.showinfo('회원가입 성공', '회원가입이 성공적으로 완료되었습니다.')
        signup_window.destroy()  # Close the signup window
        open_main_window(username)  # Open the main window

def open_signup_window():
    global entry_signup_username, entry_signup_password, entry_signup_confirm_password, signup_window

    # Hide login window
    window.withdraw()

    # Create sign-up window
    signup_window = tk.Toplevel()
    signup_window.title("Tsu - Sign Up")
    signup_window.geometry("300x350")
    signup_window.configure(bg="#f0f0f0")

    # Username label and entry
    label_username = tk.Label(signup_window, text="Username:", bg="#f0f0f0", font=("Helvetica", 12))
    label_username.pack(pady=5)

    entry_signup_username = tk.Entry(signup_window, bg="#f9f9f9", font=("Helvetica", 12))
    entry_signup_username.pack(pady=5)

    # Password label and entry
    label_password = tk.Label(signup_window, text="Password:", bg="#f0f0f0", font=("Helvetica", 12))
    label_password.pack(pady=5)

    entry_signup_password = tk.Entry(signup_window, show="*", bg="#f9f9f9", font=("Helvetica", 12))
    entry_signup_password.pack(pady=5)

    # Confirm Password label and entry
    label_confirm_password = tk.Label(signup_window, text="Confirm Password:", bg="#f0f0f0", font=("Helvetica", 12))
    label_confirm_password.pack(pady=5)

    entry_signup_confirm_password = tk.Entry(signup_window, show="*", bg="#f9f9f9", font=("Helvetica", 12))
    entry_signup_confirm_password.pack(pady=5)

    # Sign up button
    signup_button = tk.Button(signup_window, text="Sign Up", command=signup, bg="#007bff", fg="#ffffff",
                              font=("Helvetica", 12, "bold"))
    signup_button.pack(pady=10, ipadx=20, ipady=3)

    signup_window.mainloop()


# Create a Tkinter window for login
window = tk.Tk()
window.title("Tsu - Login")
window.geometry("300x350")
window.configure(bg="#f0f0f0")

# App Name
app_font = tkfont.Font(family="Helvetica", size=24, weight="bold")
label_app_name = tk.Label(window, text="Tsu", font=app_font, bg="#f0f0f0")
label_app_name.pack(pady=20)

# Create a frame for login
frame_login = tk.Frame(window, bg="#f0f0f0")
frame_login.pack(pady=10)

# Username label and entry
label_username = tk.Label(frame_login, text="Username:", bg="#f0f0f0", font=("Helvetica", 12))
label_username.grid(row=0, column=0, pady=5)

entry_login_username = tk.Entry(frame_login, bg="#f9f9f9", font=("Helvetica", 12))
entry_login_username.grid(row=0, column=1, pady=5)

# Password label and entry
label_password = tk.Label(frame_login, text="Password:", bg="#f0f0f0", font=("Helvetica", 12))
label_password.grid(row=1, column=0, pady=5)

entry_login_password = tk.Entry(frame_login, show="*", bg="#f9f9f9", font=("Helvetica", 12))
entry_login_password.grid(row=1, column=1, pady=5)

# Login button
login_button = tk.Button(window, text="Login", command=login, bg="#007bff", fg="#ffffff",
                         font=("Helvetica", 12, "bold"))
login_button.pack(pady=10, ipadx=20, ipady=3)

# Membership button
membership_button = tk.Button(window, text="Create Account", command=open_signup_window, bg="#28a745", fg="#ffffff",
                              font=("Helvetica", 12, "bold"))
membership_button.pack(pady=5, ipadx=10, ipady=3)

window.mainloop()
