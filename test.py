import csv
import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split

# 랜덤 시드 설정
RANDOM_SEED = 42

# 파일 경로 설정
dataset = 'C:/Users/kimdonghan/PycharmProjects/python_signLangs_project/model/keypoint_classifier/keypoint.csv'
model_save_path = 'C:/Users/kimdonghan/PycharmProjects/python_signLangs_project/model/keypoint_classifier/keypoint_classifier.hdf5'

# 분류할 클래스의 수
NUM_CLASSES = 10

# CSV 파일에서 X 데이터(손동작의 특성)와 y 데이터(레이블)을 로드
X_dataset = np.loadtxt(dataset, delimiter=',', dtype='float32', usecols=list(range(1, 21 * 2 + 1)))
y_dataset = np.loadtxt(dataset, delimiter=',', dtype='int32', usecols=(0))

# 데이터를 학습용과 테스트용으로 분할
X_train, X_test, y_train, y_test = train_test_split(X_dataset, y_dataset, train_size=0.75, random_state=RANDOM_SEED)

# 신경망 모델 구성
model = tf.keras.models.Sequential([
    tf.keras.layers.Input((42,)),  # 21*2 특성 입력
    tf.keras.layers.Dropout(0.2),
    tf.keras.layers.Dense(20, activation='relu'),
    tf.keras.layers.Dropout(0.4),
    tf.keras.layers.Dense(10, activation='relu'),
    tf.keras.layers.Dense(NUM_CLASSES, activation='softmax')
])

# 모델 저장과 조기 종료를 위한 콜백 설정
cp_callback = tf.keras.callbacks.ModelCheckpoint(
    model_save_path, verbose=1, save_weights_only=False)
es_callback = tf.keras.callbacks.EarlyStopping(patience=20, verbose=1)

# 모델 컴파일
model.compile(
    optimizer='adam',
    loss='sparse_categorical_crossentropy',
    metrics=['accuracy']
)

# 모델 학습
model.fit(
    X_train,
    y_train,
    epochs=1000,
    batch_size=128,
    validation_data=(X_test, y_test),
    callbacks=[cp_callback, es_callback]
)

# 테스트 데이터로 모델 평가
val_loss, val_acc = model.evaluate(X_test, y_test, batch_size=128)
model = tf.keras.models.load_model(model_save_path)

# 예측 결과 출력
predict_result = model.predict(np.array([X_test[0]]))
print(np.squeeze(predict_result))
print(np.argmax(np.squeeze(predict_result)))
model.save(model_save_path, include_optimizer=False)
tflite_save_path = 'model/keypoint_classifier/keypoint_classifier.tflite'

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
tflite_quantized_model = converter.convert()

open(tflite_save_path, 'wb').write(tflite_quantized_model)

interpreter = tf.lite.Interpreter(model_path=tflite_save_path)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

interpreter.set_tensor(input_details[0]['index'], np.array([X_test[0]]))
interpreter.invoke()
tflite_results = interpreter.get_tensor(output_details[0]['index'])
print(np.squeeze(tflite_results))
print(np.argmax(np.squeeze(tflite_results)))