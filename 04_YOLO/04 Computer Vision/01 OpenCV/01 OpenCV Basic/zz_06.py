import cv2

img= cv2.imread('images/pome.png', cv2.IMREAD_GRAYSCALE)
cv2.imshow('gray image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()

result= cv2.imwrite('saved/img.jpg', img)
print('저장결과:', result)

img2= cv2.imread('images/receipt.jpg', cv2.IMREAD_GRAYSCALE)
cv2.imwrite('saved/img2.png', img2)

# 동영상 저장~
cap= cv2.VideoCapture('videos/dog_sd.mp4')

fourcc= cv2.VideoWriter_fourcc(*'MP4V')

width= cap.get(cv2.CAP_PROP_FRAME_WIDTH)
height= cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
fps= cap.get(cv2.CAP_PROP_FPS) * 3

width= round(width)
height= round(height)

out= cv2.VideoWriter(filename='saved/output.mp4', fourcc=fourcc, fps=fps, frameSize=(width,height))

while cap.isOpened():
    ret, frame= cap.read()
    if not ret:
        break

    out.write(frame)
    cv2.imshow('dog video', frame)
    if cv2.waitKey(33) == ord('q'):
        break

out.release()
cap.release()
cv2.destroyAllWindows()