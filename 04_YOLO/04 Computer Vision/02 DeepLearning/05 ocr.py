# 사진 속 한글과 영어를 자동으로 찾아 텍스트로 추출하기 : OCR (Optical Character Recognition)
#EasyOCR 모듈 사용

#모듈 설치
#pip install easyocr

#0. 모듈 사용
import cv2
import easyocr
import numpy as np

#1. 이미지 불러오기(글씨가 포함된 이미지)
# img= cv2.imread('images/ocr_korean.png')
# img= cv2.imread('images/ocr_english.png')
img= cv2.imread('images/ocr_example.png')
img= cv2.imread('images/ocr_document.png')
img= cv2.imread('images/ocr_receipt2.jpg')
#영수증처럼. 격자형태(표)구조는 paddleocr 이 더 좋은 성능을 보여줌.

#2. EasyOCR 객체 생성
reader= easyocr.Reader(['ko','en'], gpu=False)
#최초 실행될 때 각 언어별 모델을 다운로드 함.

#3. 글씨가 포함된 이미지에서 문자를 검출 및 인식
results= reader.readtext(img)
#반환값 : (boundingbox, 인식문자, 신뢰도)
#boundingbox: 문자 영역의 네 꼭짓점 좌표
#text: 인식된 문자
#confidence: 문자 인식 신뢰도 점수

#4. 인식결과 출력 및 사각형 영역도 표시
result_img= img.copy()
for i, (bbox, text, confidence) in enumerate(results, 1):  #반복문의 i의 순번을 0이 아닌 1부터..
    #인식된 문자와 신뢰도를 출력
    print(f"{i} : {text} (신뢰도: {confidence:.3f})")

    # 문자가 있는 위치 영역 bounding box 표시 - 다각형 그리기로 연습해보기
    points= np.array(bbox, dtype=np.int32)
    cv2.polylines(result_img, [points], True, (0,255,0), 3)  #True: 닫힌 다각형 그리기

    #사각형 위치마다 번호를 표시
    x,y= points[0]  #좌상단 좌표만.. 사용
    cv2.putText(result_img, str(i), (x,y-5), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255),2)
#-------------------------

#5. 결과 이미지를 출력 및 저장
print('검출된 문자 영역의 개수:', len(results))

cv2.imshow('original', img)
cv2.imshow('ocr result', result_img)

cv2.imread('output/ocr_result.jpg', result_img)

cv2.waitKey(0)
cv2.destroyAllWindows()

#혹시 imshow()에서 에러가 발생한다면..
#opencv-python-headless 모듈과 기존 opencv-python의 충돌 문제 발생.

#제거 후 재설치
#pip uninstall opencv-python-headless
#pip uninstall opencv-python

#pip install opencv-python


