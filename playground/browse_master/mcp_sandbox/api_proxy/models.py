# Define request body models
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


class WebParseRequest(BaseModel):
    link: str
    user_prompt: str
    llm: str = "gpt-4o"


class BatchSearchRequest(BaseModel):
    keyword: str


class GenerateKeywordsRequest(BaseModel):
    seed_keyword: str


class CheckConditionRequest(BaseModel):
    content: str
    condition: str


