# object oriented programming : 객체 지향 프로그래밍

# 연관있는 변수를 묶어서 관리, 이 변수를 제어하는 기능함수도 함께 그룹화 - 클래스로 설계하고 객체를 만들어 사용

class Person:
    # 이 Person 클래스가 객체가 될 때 자동으로 실행되는 초기화 함수 (다른 언어에서는 생성자 함수)
    def __init__(self, name='익명', age=0, address='무연고자'):
        self.name= name
        self.age= age
        self.address= address

    # 멤버변수의 값을 출력하는 기능함수를 설계 -- 멤버함수 -- 메소드 method
    def show(self):
        print('name:', self.name)
        print('age:', self.age)
        print('address:', self.address)


# 위에서 만든 설계도(class)를 사용하려면.. 제품(객체object)를 만들어야 함.
p1= Person()  # 초기화 함수 발동
print(p1.name, p1.age, p1.address)  #멤버변수 사용

p2= Person('sam', 20, 'seoul')
p2.show()

# ----- 상속 ----- 기존에 있는 클래스를 가져와서 필요한 멤버만 추가하여 설계하는 간편한 문법
# 이름, 나이, 주소, 전공 정보를 가진 학생 데이터 필요... 이 데이터를 묶어서 관리하기 위해 클래스 설계
class Student(Person):  #이미 Person 클래스의 이름, 나이, 주소 멤버변수를 보유함
    def __init__(self, name, age, address, major):
        super().__init__(name, age, address)  #부모 클래스에서 알아서 멤버에 값 대입
        self.major= major

    # 상속받은 show()기능을 다시 구현.. override
    def show(self):
        super().show()
        print('major:', self.major)

stu1= Student('robin',22,'busan','ai')
stu1.show()

