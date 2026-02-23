# BASE TOOL API Documentation

---

## 📚 Table of Contents

* [1. Web Search](#1-web-search)
* [2. Web Content Retrieval](#2-web-content-retrieval)
* [4. Paper Content Retrieval](#4-paper-content-retrieval)
* [5. Web Parsing](#5-web-parsing)
* [6. Paper Parsing](#6-paper-parsing)
* [7. Configuration File Description](#7-configuration-file-description)
* [8. Service Monitoring](#8-service-monitoring)

---

## 1. Web Search

**File**: `api_utils/web_search_api.py`

### `google_search`

Calls Google API to perform web search.

* **Configuration Path**: Set `"serper_api_key"` in `configs/web_agent.json`
* **Input Parameters**:

  * `query`: Search keyword
  * `top_k`: Number of results to return
* **Output Example**:

```json
{
  "knowledgeGraph": {
    // (some keywords might include) knowledge graph information related to search content
  },
  "organic": [
    {
      "title": "Example Title",
      "link": "https://example.com",
      "snippet": "Web page summary information",
      "sitelinks": [
        {
          "title": "Sub-link title",
          "link": "https://example.com/page"
        },
        ...
      ],
      "position": 1
    }
  ],
  "relatedSearches": [
    {
      "query": "Related search term"
    },
    ...
  ]
}
```

---

## 2. Web Content Retrieval

**File**: `api_utils/fetch_web_page_api.py`

---

### `download_htmlpage`

Directly downloads the HTML content of a web page.

* **Input Parameters**:

  * `url`: Web page link
  * `timeout`: Timeout (in seconds)
* **Output**: Raw HTML content as a string

---

### `get_web_content_api`

Downloads the web page content using an API (⚠️ **Does not support downloading Google pages**).

* **Configuration Path**: Set `"serper_api_key"` in `configs/web_agent.json`
* **Input Parameters**:

  * `url`: Web page link
* **Output**: Main content text of the web page

---

### `fetch_web_content`

Final web download function, with the following logic:

1. First, attempts to call `download_htmlpage`.
2. If it fails, automatically falls back to calling `get_web_content_api`.

---

## 4. Paper Retrieval

**File**: `api_utils/pdf_read_api.py`

### `read_pdf_from_url`

Fetches the full content of a paper via PDF link.

* **Function Description**: Downloads the specified paper's PDF file and extracts all the text content (returns as a string).

* **Input Parameters**:

  * `url`: Paper PDF file link (supports HTTPS links)

* **Output**:

  * Extracted full text content of the paper (as a string, suitable for further NLP processing, summarization, question answering, etc.)

---

## 5. Web Parsing: `parse_htmlpage`

**File**: `MCP/server/BASE-TOOL-Server/web_agent/web_parse.py`

---

### Function: `parse_htmlpage`

Uses the specified LLM to parse a web page and generate a structured summary.

* **Function Description**:

  * Calls `fetch_web_content` to fetch the web page content.
  * Uses LLM to semantically summarize the web content (model usage is configurable).
  * Supports extracting main points and structured information from the content.

* **Configuration Path**:

  * In `configs/common_config.py`, configure "gpt-4o", "gpt-4.1-nano-2025-04-14", and "qwen-32b" for `url` and `api key`.
  * In `configs/web_agent.json`, configure `"USE_MODEL"` (for parsing LLM) and `"BASE_MODEL"` (fallback LLM).

* **Input Parameters**:

  | Parameter Name | Type  | Description                                                                              |
  | -------------- | ----- | ---------------------------------------------------------------------------------------- |
  | `url`          | `str` | Web page link                                                                            |
  | `user_prompt`  | `str` | User prompt or task instruction, e.g., `"Summarize page content"`                        |
  | `llm`          | `str` | (Optional) LLM model name to use, e.g., `"gpt-4o"`. If empty, the default model is used. |

* **Output**:

  * Returns a JSON object in the following format:

  ```json
  {
    "content": "LLM generated web page summary or result",
    "urls": ["Relevant links extracted from the page (if any)"],
    "score": "Relevance_score"
  }
  ```

---

## 6. Paper Parsing

**File Location**: `MCP/server/BASE-TOOL-Server/paper_agent/paper_parse.py`

---

### Function: `paper_qa_link`

Extracts text from a paper PDF link and generates structured answers combined with user queries using a large language model.

* **Function Description**:

  * Downloads and parses the full text of the paper.
  * Automatically splits content to avoid long input.
  * Uses LLM (large language model) for question-answer analysis on paper content.

* **Configuration Path**:

  * In `configs/common_config.py`, configure "gpt-4o", "gpt-4.1-nano-2025-04-14", and "qwen-32b" for `url` and `api key`.
  * In `configs/paper_agent.json`, configure `"USE_MODEL"` (for parsing LLM) and `"BASE_MODEL"` (fallback LLM).

* **Input Parameters**:

  | Parameter Name | Type  | Description                                                      |
  | -------------- | ----- | ---------------------------------------------------------------- |
  | `link`         | `str` | PDF link (e.g., from ArXiv)                                      |
  | `query`        | `str` | User query, e.g., `"What is the main innovation of this paper?"` |
  | `llm`          | `str` | (Optional) Model name to use, e.g., `"gpt-4o"`                   |

* **Output**:

  * Returns a JSON object with the following structure:

  ```json
  {
    "content": "LLM generated response",
    "urls": [],
    "score": 1
  }
  ```

---

## 7. Related Configuration Files

* `configs/paper_agent.json`
* `configs/web_agent.json`
* `configs/common_config.py`

