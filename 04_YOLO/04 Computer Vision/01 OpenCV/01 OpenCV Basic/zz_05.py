import cv2
import numpy as np
img= np.zeros((480, 640, 3), dtype=np.uint8)

COLOR= (0,255,255)
THICKNESS= 1
SCALE= 1

cv2.putText(img, 'Hello opencv', (20,50), cv2.FONT_HERSHEY_SIMPLEX,SCALE, COLOR, THICKNESS)
cv2.putText(img, 'Hello opencv', (20,80), cv2.FONT_HERSHEY_PLAIN,SCALE, COLOR, THICKNESS)
cv2.putText(img, 'Hello opencv', (20,110), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,SCALE, COLOR, THICKNESS)
cv2.putText(img, 'Hello opencv', (20,140), cv2.FONT_HERSHEY_TRIPLEX,SCALE, COLOR, THICKNESS)
cv2.putText(img, 'Hello opencv', (20,170), cv2.FONT_HERSHEY_SCRIPT_COMPLEX,SCALE, COLOR, THICKNESS)
cv2.putText(img, 'Hello opencv', (20,200), cv2.FONT_HERSHEY_SCRIPT_COMPLEX|cv2.FONT_ITALIC,SCALE, COLOR, THICKNESS)

cv2.putText(img, '안녕하세요~', (20,230), cv2.FONT_HERSHEY_SCRIPT_COMPLEX|cv2.FONT_ITALIC,SCALE, COLOR, THICKNESS)

from PIL import Image, ImageDraw, ImageFont

def draw_custom_font(img, text, position, font_path, font_size, color):
    img_rgb= cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img= Image.fromarray(img_rgb)

    draw= ImageDraw.Draw(pil_img)
    font= ImageFont.truetype(font_path, font_size)
    draw.text(position, text, font=font, fill=color)

    img_bgr= cv2.cvtColor(np.array(pil_img), cv2.COLOR_BGR2RGB)
    return img_bgr

font_path= 'fonts/sebang.ttf'
text_position= (300,100)
text_color= (255,255,0)

img= draw_custom_font(img, "good 굳 good 굳 good 굳", text_position, font_path, 30, text_color)


#----------------------------------------------------------
cv2.imshow('image & text', img)
cv2.waitKey(0)
cv2.destroyAllWindows()