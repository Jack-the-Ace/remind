#1. 표준(내장) 모듈 -- 별도의 추가 설치 없이  import를 통해 사용
import math
print("루트 16 =", math.sqrt(16))  # 거듭제곱: 4**3 = math.pow(4,3)

import random
print("점심 메뉴 선정:", random.choice(['김밥','라면','비빔밥']))

# import datetime
# print('현재시간:', datetime.datetime.now())

from datetime import datetime
print('현재시간:', datetime.now())
print('현재시간:', datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분"))
print()

#2. 외부 모듈 -- 별도의 설치가 필요 -- 패키지(모듈:라이브러리) 설치 도구 pip
# 먼저. 설치목록 확인  pip list

#1) HTTP 통신을 위한 외부 모듈 requests   -----------  여러버전 중 3.15버전에 설치할때 : python3.15 -m pip install requests
import requests
response= requests.get('https://example.com', timeout=5)
print('응답코드:', response.status_code)  # 200 OK, 404 & 403 error
print('응답글씨:', response.text)

# 여러개의 모듈을 한 번에 설치.
# numpy, pandas, matplotlib, selenium
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

aaa= np.array([10,20,30])
print(aaa.mean())

bbb= pd.DataFrame({
    "name":['sam','robin','hong'],
    "score":[80,95,70]
})
print(bbb)
print(round(bbb['score'].mean(),3))

plt.figure(figsize=(5,3))
plt.bar(bbb['name'], bbb['score'])
plt.title('student scores')
plt.ylim(0,100)
plt.tight_layout()
#plt.show()

from pathlib import Path
BASE_DIR= Path(__file__).resolve().parent
save_path= BASE_DIR / "student_scores.png"
plt.savefig(save_path)
plt.close()

# 웹 브라우저 자동화 모듈 - RPA 작업 또는 AI Agent 만들 때 활용 가능.
from selenium import webdriver
chrome= webdriver.Chrome()
chrome.get('https://naver.com')

import time
from selenium.webdriver.common.by import By

time.sleep(2)
search_box= chrome.find_element(By.ID, "query")
search_box.send_keys('스타벅스')
time.sleep(2)

from selenium.webdriver.common.keys import Keys
search_box.send_keys(Keys.ENTER)
time.sleep(3)

#--- 가상환경 만들기 복습 ---
# python3.11 -m venv venv
# venv/Scripts/activate -- windows, macos: source venv/bin/activate

# 가상환경 종료 : deactivate

