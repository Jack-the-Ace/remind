#사진 속 한글과 영어를 자동으로 찾아 텍스트로 추출하기: OCR (Optical character Recognition)
# EasyOCR 모듈 사용

#모듈 설치
# pip install easyocr

import cv2
import easyocr
import numpy as np

img= cv2.imread('images/ocr_example.png')

reader= easyocr.Reader(['ko','en'], gpu=False)

results= reader.readtext(img)

result_img= img.copy()
for i, (bbox, text, confidence) in enumerate(results, 1):
    print(f"{i} : {text} (신뢰도: {confidence:.3f})")

    points= np.array(bbox, dtype=np.int32)
    cv2.polylines(result_img, [points], True, (0,255,0), 3)

    x,y= points[0]
    cv2.putText(result_img, str(i), (x,y-5), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
#-------------------------
print('검출된 문자 영역의 개수:', len(results))

cv2.imshow('original', img)
cv2.imshow('ocr result', result_img)

cv2.imwrite('output/ocr_result.jpg', result_img)

#-----
cv2.waitKey(0)
cv2.destroyAllWindows()