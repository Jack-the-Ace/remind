# opencv로 이미지 처리 후 파일로 저장하기
import cv2

#1. 흑백으로 이미지를 불러오고 파일로 저장하기
img= cv2.imread('images/dog3.jpg', cv2.IMREAD_GRAYSCALE)
cv2.imshow('gray image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()

#파일로 저장
result=cv2.imwrite('saved/img.jpg', img)
print('저장결과:', result)

img2= cv2.imread('images/cat.png', cv2.IMREAD_GRAYSCALE)
cv2.imwrite('saved/img2.png', img2)

#2. 동영상 저장
cap= cv2.VideoCapture('videos/dog_sd.mp4')

#동영상을 저장하려면 코덱이 필요함
fourcc= cv2.VideoWriter_fourcc(*'MP4V') # * : 언패킹 연산자 -- 문자열을 하나씩 풀어버리는 연산자.. // 원래는 이렇게 써야함 ('M','P','4','V')
# four character code : 4글자 문자로 된 코덱 구분자
#예) DIVX, XVID, MP4V, H264, MJPG
# .avi --> DIVX를 썼었음(예전거라서 요즘 플레이어들은 기본 설치 안되어있음.)
# .mp4 --> 웹,데스크탑,앱 모두 구동 가능한 코덱. 요즘 가장 대중적

#원본과 같은 크기, 속도로 저장
width= cap.get(cv2.CAP_PROP_FRAME_WIDTH)
height= cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
fps= cap.get(cv2.CAP_PROP_FPS) * 3   # 곱하기3 (*3) 이런식으로도 가능 (안하면 원래속도)

#동영상의 너비는 정수만 가능
width= round(width)
height= round(height)

#비디오 저장객체 생성(저장할 곳의 파일명, 재생속도, 크기)
out= cv2.VideoWriter(filename='saved/output.mp4', fourcc=fourcc, fps=fps, frameSize=(width, height))

#프레임단위로 원본에서 동영상을 가져와서 새로운 동영상으로 만들기
while cap.isOpened():
    ret, frame= cap.read()  #한 프레임 읽기
    if not ret:
        break

    #한장 저장
    out.write(frame)
    cv2.imshow('dog video', frame)   #장면 확인하고 싶어서...
    if cv2.waitKey(33) == ord('q'):
        break

out.release()
cap.release()
cv2.destroyAllWindows()

