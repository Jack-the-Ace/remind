#RAG 시스템 워크 플로우
# ai 교육센터 이용안내 문서 --> PDF 읽기 --> 문서분할(청크) --> 임베딩 --> 벡터DB --> 검색결과와 질문을 LLM에게 주고 응답

# 필요한 모듈들
# pyPDF
# RecursiveCharacterSplitter : 문서 분할
# OpenAIEmbeddings :  임베딩 도구 (유료. api 사용)
# Chrome : 벡터 DB
# LangChain
# OpenAI

# 모듈 설치
# pip install -U langchain-core langchain-community langchain-text-splitters langchain-openai langchain-chroma langchain pypdf

#0. 사용하는 모듈 import (work flow 순서로 쓴다면↓)
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

#1. PDF 문서 읽기
from pathlib import Path
pdf_path= Path(__file__).with_name('ai_course_guide.pdf')
docs= PyPDFLoader(str(pdf_path)).load()
print(len(docs))

#2. 문서를 작은 조각으로 분할 -- 청크
chunks= RecursiveCharacterTextSplitter(
    chunk_size= 450,
    chunk_overlap= 90
).split_documents(docs)
print(len(chunks))

#3. 임베딩 및 Chroma 벡터 DB 생성
from dotenv import load_dotenv
load_dotenv()

embeddings= OpenAIEmbeddings(model='text-embedding-3-small')
vector_db= Chroma.from_documents(chunks, embeddings)

# 관련문서 검색해주는 검색기 생성
retriever= vector_db.as_retriever(search_kwargs={"k":2})

#5. 랭체인 연결을 위해 LLM과 프롬프트 생성
llm = ChatOpenAI(model='gpt-4o-mini', temperature=0)
prompt= ChatPromptTemplate.from_messages([
    ('system','제공된 자료만 근거로 한국어로 답하세요. 자료에 답이 없으면 "문서에서 확인할 수 없습니다."라고 답하세요.'),
    ('human','[자료]\n{context}\n\n[질문]\n{question}')
])
chain= prompt | llm | StrOutputParser()

#6. 질문 --> 문서검색 --> LLM답변
print('RAG 채팅 봇 시작!')
while True:
    question= input('\n질문: ').strip()
    if question.lower()=='exit':
        break

    if not question:
        continue

    # 질문과 유사한 문서 검색
    found= retriever.invoke(question)
    context= "\n\n".join( d.page_content for d in found)

    # 검색된 문서와 질문을 LLM에게 주고 답변 받기
    answer= chain.invoke({'context':context, 'question':question})
    print('AI: ', answer)





