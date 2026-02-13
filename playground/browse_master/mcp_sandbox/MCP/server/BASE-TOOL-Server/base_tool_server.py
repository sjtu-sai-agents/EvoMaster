import asyncio
import logging
from mcp.server.fastmcp import FastMCP
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

mcp = FastMCP("base_tool")

def get_content_type(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=3)
        return response.headers.get('Content-Type', '').lower()
    except requests.RequestException:
        return "None"

@mcp.tool()
async def web_search(query: str,top_k: int = 10):
    """
    Use google search engine to search information from the web for the given query.

    Args:
        query (str): The search query to submit to the search engine. 
        top_k (int): The number of results to return.
    
    Returns:
        dict: A dictionary with:
            - knowledgeGraph: The knowledge graph of the search result.
            - organic: The result of the web page search.
                - title: The title of the web page.
                - link: The URL of the web page.
                - snippet: The snippet of the web page.
                - sitelinks: The sitelinks of the web page.
            - relatedSearches: The related searches of the search result.
    """
    from web_agent.web_search import google_search
    result = await google_search(query,top_k)
    return result

@mcp.tool()
async def web_parse(link: str,user_prompt: str,llm: str = "gpt-4o"):
    """
    web_parse is used to parse and analyze web content based on provided links and queries.

    Args:
        link (str): The URL link to the web content
        user_prompt (str): The specific query or analysis request about the web content
        llm (str): The LLM model to use for parsing the web content

    Returns:
        dict: A dictionary with:
            - content: The parsed content of the web page according to the user's prompt.
            - urls: The URLs on the web page which are related to the user's prompt.
            - score: The score of the web page.
    """
    
    if ".pdf" in link or 'arxiv.org/abs' in link or  'arxiv.org/pdf' in link or "pdf" in get_content_type(link):
        from paper_agent.paper_parse import paper_qa_link
        response = await paper_qa_link(link,user_prompt,llm)
    else:
        from web_agent.web_parse import parse_htmlpage
        response = await parse_htmlpage(link,user_prompt,llm)
    return response



if __name__ == "__main__":
    logging.info("Starting MCP Server with all base tools...")
    mcp.run(transport="stdio")

