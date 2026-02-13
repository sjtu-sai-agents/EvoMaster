# 定义请求体的模型
from matplotlib.pyplot import cla
from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    serper_api_key: str = ""
    top_k: int = 10
    region: str = "us"
    lang: str = "en"
    depth: int = 0



class SearchPaperInfo(BaseModel):
    query:str


class ReadPdfInfo(BaseModel):
    url:str


class FetchWebContent(BaseModel):
    url:str   


