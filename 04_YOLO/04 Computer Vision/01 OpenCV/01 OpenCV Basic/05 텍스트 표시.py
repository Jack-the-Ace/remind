import cv2
import numpy as np
img= np.zeros((480,640,3), dtype=np.uint8)

# 글자 표시.
COLOR= (255,255,255)  #글씨 색상 - 백색
THICKNESS= 1          #글씨 선 두께
SCALE= 1              #글씨 크기 비율

#1) 기본 폰트별 글씨 표시하기 : 이미지, 텍스트내용, 글씨의 좌하단좌표, 글꼴, 크기, 색상, 두께
cv2.putText(img, 'Hello opencv', (20,50), cv2.FONT_HERSHEY_SIMPLEX, SCALE, COLOR, THICKNESS)  #보통크기의 sans-serif
cv2.putText(img, 'Hello opencv', (20,100), cv2.FONT_HERSHEY_PLAIN, SCALE, COLOR, THICKNESS)  #작은크기의 sans-serif
cv2.putText(img, 'Hello opencv', (20,150), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, SCALE, COLOR, THICKNESS)  #필기체 스타일
cv2.putText(img, 'Hello opencv', (20,200), cv2.FONT_HERSHEY_TRIPLEX, SCALE, COLOR, THICKNESS)  #보통크기의 serif
cv2.putText(img, 'Hello opencv', (20,250), cv2.FONT_HERSHEY_SCRIPT_COMPLEX, SCALE, COLOR, THICKNESS)  #필기체
cv2.putText(img, 'Hello opencv', (20,300), cv2.FONT_HERSHEY_SCRIPT_COMPLEX | cv2.FONT_ITALIC, SCALE, COLOR, THICKNESS)  #필기체+이탤릭
# 기본 글꼴이 적용되지 않을 수도 있음...

# 원래는 한글도 안되었음... 지금은 됨..
cv2.putText(img, '안녕하세요~', (20,350), cv2.FONT_HERSHEY_SIMPLEX, SCALE, COLOR, THICKNESS) #필기체

#폰트 적용 (한글이 깨질때 우회방법이기도 했음.) -- 기본적으로 opencv는 외부폰트 안됨
#그래서 pillow 모듈(이미지 라이브러리)을 이용하여 글씨를 그림으로 만들어 표시하기
from PIL import Image, ImageDraw, ImageFont

#특정 폰트의 글씨를 그려내는 함수 정의 (대상 이미지, 글씨, 위치, 폰트파일경로, 폰트크기, 색상)
def draw_custom_font(img, text, position, font_path, font_size, color):
    #1. opencv 이미지(BGR)를 pillow 이미지(RGB)로 변환
    img_rgb= cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img= Image.fromarray(img_rgb)   #배열을 이미지 객체로..

    #2. pillow 를 이용하여 외부 폰트로 글씨 그리기
    draw= ImageDraw.Draw(pil_img)
    font= ImageFont.truetype(font_path, font_size)  # .ttf 파일경로, 글씨크기
    draw.text(position, text, font=font, fill=color)

    #3. pillow 이미지를 다시 opencv 이미지로 변환
    img_bgr= cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return img_bgr

#위 함수 사용하여 외부폰트 글씨 표시
font_path= "fonts/sebang.ttf"
text_position= (300,100)  #글씨 표시 위치 (좌상단. 그림을 그리는 거라서.)
text_color= (255,255,0) #RGB - yellow

img= draw_custom_font(img, "Hello. 외부폰트~@!#$", text_position, font_path, 40, text_color)

#---------------------------------------------------
cv2.imshow('image & text', img)
cv2.waitKey(0)
cv2.destroyAllWindows()




