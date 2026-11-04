#1. 저장된 모델 불러오기
model_path= "Model/k_food_model.keras"

#2. tensorflow를 이용하여 모델을 불러오기
#from tensorflow.keras.models import load_model
from keras.models import load_model
from keras.applications.efficientnet_v2 import preprocess_input  #전처리 함수

model= load_model(model_path, custom_objects={'preprocess_input':preprocess_input})

#3. 모델에 있는 출력층의 분류개수 온전하게 저장되어 있는지 확인
num_classes= model.output_shape[-1]
print('클래스 개수:', num_classes)

#4. 모델의 신경망 구조 확인
print(model.summary())

#5. 분류명은 모델에 저장되어 있지 않음. 그래서 보통 별도의 csv or txt or pickle 로 클래스명들을 저장하고 불러옴
class_names=['bibimbap', 'bob', 'bossam', 'bulgogi', 'daegaejjim', 'dakbokkeumtang', 'doenjang_chigae', 'galbijjim', 'galchijorim', 'ganjang_gejang', 'gimbob', 'jeyuk_bokkeum', 'jjajangmyeon', 'kimchi', 'nangmyeon', 'ojingeo_bokkeum', 'pajeon', 'samgupsal', 'samgyetang', 'soondae', 'soondubu_jjigae']

#6. 이미지 경로를 주면 예측해주는 함수 정의
import tensorflow as tf
from keras.preprocessing import image
import numpy as np
def predict_image(img_path):
    #이미지 경로를 통해 Tensorflow에서 인식하는 Image객체를 생성
    img = image.load_img(img_path, target_size=(224,224))
    #이미지 객체를 배열로 변환
    img_array= image.img_to_array(img)
    #3차원 텐서데이터 --> 4차원텐서 (배치사이즈추가) [배치크기,높이,너비,채널]
    img_array= tf.expand_dims(img_array, 0) #0차원 위치에 배치크기 추가

    #이미지텐서 데이터를 모델에게 주고 예측을 요청
    predictions= model.predict(img_array)
    predicted_food_name= class_names[ np.argmax(predictions) ] #분류명
    confidence= np.max(predictions) #신뢰점수-확률값

    print(f"예측: {predicted_food_name} ({confidence:.2f})")

# 클라이언트로부터 전달된 이미지 파일을 분류하도록 요청
predict_image('Test Images/image01.jpg')
predict_image('Test Images/image02.jpg')
predict_image('Test Images/image03.jpg')
