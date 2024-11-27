# Use: flask --app main --debug run

import argparse
import html
import hashlib
import json
import mimetypes
import os
import re
import tempfile
import urllib.parse
from bs4 import BeautifulSoup
from flask import Flask, request
from openai import OpenAI


def parse_arguments():
    parser = argparse.ArgumentParser(description="LLM Web Server")
    parser.add_argument("--api_url", type=str, default=None, help="API URL for the OpenAI client")
    parser.add_argument("--api_key", type=str, help="API Key for the OpenAI client")
    parser.add_argument("--persistent_cache", type=bool, default=True, help="Enable or disable persistent cache")
    parser.add_argument("--model_name", type=str, default="gpt-4o", help="Model name to use for the OpenAI client")
    parser.add_argument("--no-persistent_cache", action='store_true', help="Disable persistent cache")
    parser.add_argument("--base_url", type=str, default="http://localhost:5000/", help="Base URL for the server")
    parser.add_argument("--base_prompt", type=str, default="prompts/base_prompt.txt", help="Path to the base prompt file")
    parser.add_argument("--css_prompt", type=str, default="prompts/css_prompt.txt", help="Path to the base prompt file")
    parser.add_argument("--inject_script", type=str, default="injectScript.js", help="Path to the script to be injected into all webpages.")
    return parser.parse_args()

args = parse_arguments()
client = OpenAI(api_key=args.api_key, base_url=args.api_url)
with open(args.base_prompt, "r", encoding="utf-8") as file:
    BASE_PROMPT = file.read()
with open(args.css_prompt, "r", encoding="utf-8") as file:
    CSS_PROMPT = file.read()
with open(args.inject_script, "r", encoding="utf-8") as file:
    INJECT_SCRIPT = file.read()
with open("index.html", "r", encoding="utf-8") as file:
    INDEX_HTML = file.read()


print(CSS_PROMPT)



# ------ #
# Helper #
# ------ #


def extract_first_code_block(text: str) -> str:
    """
    Extracts the content of the first code block from the given text.
    Args:
        text (str): The input text containing one or more code blocks.
    Returns:
        str: The content of the first code block if found, otherwise the original text.
    """
    # Regular expression to capture the content of the first code block
    pattern = r'```(?:\w+)?\s*([\s\S]*?)\s*```'
    
    # Search for the first occurrence of the pattern
    match = re.search(pattern, text)
    
    # If a match is found, return the captured content; otherwise, return None or an empty string
    if match:
        return match.group(1).strip()
    else:
        return text


def prepend_current_domain(html_string, domain=""):
    """
    Prepend the current domain to specific attributes in HTML tags within the given HTML string.

    This function processes an HTML string and prepends the specified domain to the 'href', 'src', 
    and 'action' attributes of relevant tags. It also processes 'link' tags with rel="stylesheet" 
    and modifies 'script' tags to replace 'http://' and 'https://' with '/https://'. Additionally, 
    it removes 'script' tags containing the word "dynamic".

    Args:
        html_string (str): The HTML content as a string.
        domain (str, optional): The domain to prepend to the attributes. Defaults to an empty string.

    Returns:
        str: The modified HTML content as a string.
    """
    soup = BeautifulSoup(html_string, 'html.parser')
    tags_attributes = ['href', 'src', 'action']

    def prepend_to_attribute(tag, attribute):
        value = tag.get(attribute)

        # remove query_section, just in case it exists
        if attribute == "href":
            print("replacing", value, domain)
            value = re.sub(r'\?query_section=[a-zA-Z0-9_]+', '', value)

        if value and not value.startswith("#"):
            if value.startswith("/"):
                if domain.endswith("/"):
                    tag[attribute] = f"/{domain[:-1]}{value}" if domain != "/" else f"{value}"
                else:
                    tag[attribute] = f"/{domain}{value}" if domain != "/" else f"{value}"
            else:
                tag[attribute] = f"/{value}"

        # Check if the tag is a link rel="stylesheet"
        if tag.name == "link" and tag.get("rel") == ["stylesheet"]:
            href_value = tag.get("href")
            if href_value and "http" not in href_value:
                tag["href"] = f"/{domain}{href_value}" if not domain.endswith("/") else f"/{domain[:-1]}{href_value}"

    for attr in tags_attributes:
        for t in soup.find_all(attrs={attr: True}):
            if t.name == "img":
                continue
            prepend_to_attribute(t, attr)

    script_tags = soup.find_all('script')
    for script in script_tags:
        if script.string:  # Ensure the script tag has text content
            # Replace http:// and https:// with abc://
            updated_script_content = re.sub(r'https?://', f'/https://', script.string)
            script.string.replace_with(updated_script_content)

            # heuristic to remove all scripts involving the dynamic tag
            if script.string and "dynamic" in script.string:
                script.decompose()

    return str(soup)


# ------- #
# Caching #
# ------- #

# Define the temporary directory for caching
cache_dir = tempfile.gettempdir() if args.persistent_cache and not args.no_persistent_cache else tempfile.mkdtemp()
print("Cache Dir:", cache_dir)

def _get_cache_file_path(url):
    # Generate a unique filename based on the URL hash
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    return os.path.join(cache_dir, f"{url_hash}.cache")

def load_cached(url):
    cache_file_path = _get_cache_file_path(url)
    if os.path.exists(cache_file_path):
        with open(cache_file_path, 'r', encoding="utf-8") as cache_file:
            cached_data = json.load(cache_file)
            return cached_data.get('content'), cached_data.get('content_type')
    return None, None

def save_cached(url, content, content_type):
    cache_file_path = _get_cache_file_path(url)
    cache_data = {
        'content': content,
        'content_type': content_type
    }
    with open(cache_file_path, 'w', encoding="utf-8") as cache_file:
        json.dump(cache_data, cache_file)



# ------------ #
# Flask Server #
# ------------ #

app = Flask(__name__)

@app.route("/", methods = ['POST', 'GET'])
@app.route("/<path:path>", methods = ['POST', 'GET'])
def catch_all(path=""):

    # Get the query string arguments and fragment
    query_string = request.query_string.decode('utf-8')
    fragment = request.url.split('#')[1] if '#' in request.url else ''

    # Reconstruct the URL without the domain
    url = path
    if query_string:
        url += '?' + query_string
    if fragment:
        url += '#' + fragment

    # divide url into domain and path
    url = url.replace("https://", "").replace("http://", "")
    if "/" in url:
        domain, url = url.split("/", 1)
    else:
        domain, url = url, ""

    if url.endswith(".css/"):
        url = url[:-1]

    # show index
    if path == "":
        return INDEX_HTML, 200, {"Content-Type": "text/html"}

    # reconstruct the "virtual" URL
    full_url = f"{domain}/{url}"
    print(f"DOMAIN/URL={domain}/{url}")

    additional_data = request.form.to_dict() or {}
    additional_data_str = json.dumps(additional_data, sort_keys=True)  # Convert dict to sorted JSON string
    cache_key = f"{full_url}+{additional_data_str}"
    unescaped_full_url = urllib.parse.unquote(full_url)
    user_request = json.dumps({"url": unescaped_full_url, **additional_data}, ensure_ascii=False)
    print("User requested:", user_request)

    # use cache
    cached, content_type = load_cached(cache_key)
    if cached:
        return cached, 200, {"Content-Type": content_type}

    # skip favicon creation
    if request.path.endswith(("favicon.ico", ".png", ".jpg", ".jpeg", ".gif", ".ico")):
        return "", 200, {}

    # get content type
    content_type, _ = mimetypes.guess_type(full_url.split("?")[0])
    if content_type is None:
        content_type = 'text/html'
    if ".css" in full_url:
        content_type = "text/css"

    # fill in data into prompt
    #   - OPTIONAL_DATA -> POST request data (for forms, etc.)
    #   - URL_PATH -> virtual url
    #   - FILE_TYPE -> content_type
    print("content-type", content_type)
    prompt_used = CSS_PROMPT if "css" in content_type else BASE_PROMPT
    prompt = prompt_used
    prompt = prompt.replace("{{URL_PATH}}", full_url)
    prompt = prompt.replace("{{FILE_TYPE}}", content_type)

    # api call

    response = client.chat.completions.create(
        model=args.model_name,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_request}
        ],
        temperature=0.0,
        max_tokens=4096,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    response_data = response.choices[0].message.content

    # remove code block ticks
    response_data = extract_first_code_block(response_data)

    # silently remap all links to proxy-links (we want to keep the user in the AI web)
    try:
	    response_data = prepend_current_domain(response_data, domain+"/")
    except Exception as e:
        print("error", str(e))
        pass

    print(content_type)
    print(response_data)


    # unescape in case of javascript files
    if content_type in ["text/javascript", "text/css"]:
        response_data = html.unescape(response_data)

    # Add loadAllSections script before closing body tag
    if content_type == "text/html":
        response_data = response_data.replace(
            "</body>",
            "<script>" + INJECT_SCRIPT + "</script></body>"
        )

    # save cache
    save_cached(cache_key, response_data, content_type)

    return response_data, 200, {'Content-Type': content_type}



if __name__ == "__main__":
    app.run()
