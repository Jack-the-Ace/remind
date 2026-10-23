# 모듈 설치
# pip install langchain-core langchain-openai langchain-google-genai

# .env 파일에서 환경변수 불러오기
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

#1. 사용할 모델 선택
# llm= ChatOpenAI(model='gpt-4o-mini')
llm= ChatGoogleGenerativeAI(model='gemini-3.5-flash-lite')

#2. 프롬프트 생성
prompt= ChatPromptTemplate.from_messages([
    ('system','너는 친절한 선생님 AI 챗봇이야. 명쾌하면서도 최대한 요약된 답변을 주지.'),
    ('human','{question}')
])

#3. chain 구성 -- LCEL
chain= prompt | llm | StrOutputParser()   # | 파이프라인 연산자.. 구성요소를 체인처럼 연결

#4. 챗봇 실행
print("챗봇 시작!")
while True:
    question= input('\nHuman : ')
    if question.lower() == 'exit':
        break

    answer= chain.invoke({'question':question})
    print('AI:', answer)
