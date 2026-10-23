#1. print(), 변수, 자료형, input()
print("변수 만들고 데이터 출력")
name= '홍길동'  # 문자형(str)
age=25         # 수치형-정수(int)
height= 175.5  # 수치형-실수(float)
is_student= True # 논리값(bool)
print(name, age, height, is_student) #여러개 데이터 출력
print(f"{name}님의 나이는 {age}살 입니다.")  # f-string 출력
# 자료형을 확인하는 파이썬의 표준기능(함수) - type()
print(type(name), type(age), type(height), type(is_student))

# 키보드로 사용자 입력 데이터 받기 input()
# user_name= input('이름을 입력하세요: ').strip() or "학생"
# print(f"환영합니다. {user_name}님~!")
print()

#2. 연산자와 문자열 유용한 기능
a,b= 10,3
print('사칙연산:', a+b, a-b, a*b, round(a/b,2))
print('몫, 나머지, 제곱:', a//b, a%b, a**b)
print('비교, 논리:', a>=b, (a>5) and (b>5))

# 문자열의 여러 유용한 기능함수들
message= "     Python Review, Python      "
print(message.strip())
print(message)   #원본 불변
print(message.strip().lower())
print(message.replace('Python', '파이썬'))
print("사과,바나나,오렌지".split(','))  #응답결과는 리스트
print("Py" in message)
print(len(message))  #글자수
print()

#3. 제어문(조건, 반복)
# 점수에 따른 학점 산출
score= 72
if score >= 90:
    grade= 'A'
elif score >= 80:
    grade= 'B'
else:
    grade= 'C'
print('학점:', grade)

# 반복문
for n in range(1,6):  #1~5까지 반복
    if n==3:
        continue
    print(n)

count=0
while count<3:
    print(count)
    count += 1

#4. (제일중요) 리스트[], 튜플(), 딕셔너리{key:value}, set{}, 컴프리헨션
fruits= ["사과","바나나","사과"]  #순서대로 저장, 수정가능, 중복데이터 허용
print(fruits)
fruits.append('포도')
print(fruits)
fruits[1]= "오렌지"
print(fruits)

point= (10,20)  #튜플 - 요소 수정 불가
print(point, point[0], point[1])
# print.append()   ##존재하지 않는 기능
# point[0]= 100

student= {"name":"sam", "score":80}  #key:value pair
print(student)
student['score']=90
print(student['score'], student.get('nam','없음'))

#중복 데이터를 허용하지 않는 Set 타입
unique_fruits= set(fruits)  # list ==> set
print(unique_fruits)  # 순서는 보장 안됨. 중복 허용 안함.

# 리스트 컴프리헨션
# 1~5 의 제곱값을 저장하는 리스트 생성
squars=[ n**2 for n in range(1,6) ]
print(squars)

passing= [ n for n in [65,90,73,82] if n>=80 ]  #시험 패스 조건 통과점수들
print(passing)

#5. 함수, lambda
def greet(person, greeting='안녕하세요'):
    return f"{greeting}, {person}님!"

print( greet('영희'))
print( greet('철수','반가워용'))

def average(numbers):
    return sum(numbers) / len(numbers)  #총합/개수 = 평균 (sum, len 내장(표준)함수)
print("평균:",average([80,90,75]))

#제곱해주는 기능함수 -- 람다함수로
# def square(x):
#     return x*x
square= lambda x: x*x
print(square(5))

#내장함수 중에서 자주 사용
print('정렬:', sorted([3,1,5,2]))
print(min(3,1,5), max(3,1,5))

#6. 파일 입출력 기능함수
#현재 파일이 있는 폴더에 결과txt 문서를 저장
from pathlib import Path
BASE_DIR= Path(__file__).resolve().parent
# C:\Users\mbc\MBCA\00 심화학습 전 리마인드 수업\01_Python
file_path= BASE_DIR / "aaa.txt"

file= open(file_path, "w", encoding="utf-8")
file.write('파이썬 복습\n파일 입출력 예제\n')
file.close()

with open(file_path, "r", encoding="utf-8") as file:
    print('파일 내용:', file.read())

# 예외처리 (예외가 발생해도 다운되지 않도록..)
try:
    number= int("80abc")
    print(number+10)
except ValueError as error:
    print("예외발생:", error)
finally:
    print("예외여부와 상관없이 무조건 실행")