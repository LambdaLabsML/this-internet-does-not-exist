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
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)


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
    parser.add_argument("--dev", action='store_true', help="Enable development mode with dynamic script reloading")
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
    it removes 'script' tags containing the word "defercontent".

    Args:
        html_string (str): The HTML content as a string.
        domain (str, optional): The domain to prepend to the attributes. Defaults to an empty string.

    Returns:
        str: The modified HTML content as a string.
    """
    # print(Fore.GREEN + "Original HTML:", html_string)
    soup = BeautifulSoup(html_string, 'html.parser')
    tags_attributes = ['href', 'src', 'action']

    def prepend_to_attribute(tag, attribute):
        value = tag.get(attribute)
        print(Fore.YELLOW + f"Processing tag: {tag.name}, attribute: {attribute}, value: {value}")

        # remove query_section, just in case it exists
        if attribute == "href" and "?query_section=" in value:
            print(Fore.YELLOW + "Removing query_section from", value)
            value = re.sub(r'\?query_section=[a-zA-Z0-9_]+', '', value)

        if value and not value.startswith("#"):
            print(Fore.CYAN + f"Found {attribute}: {tag[attribute]}")
            if value.startswith("/"):
                if domain.endswith("/"):
                    tag[attribute] = f"/{domain[:-1]}{value}" if domain != "/" else f"{value}"
                else:
                    tag[attribute] = f"/{domain}{value}" if domain != "/" else f"{value}"
            else:
                tag[attribute] = f"/{value}"
            print(Fore.CYAN + f"Updated {attribute} to: {tag[attribute]}")

        # Check if the tag is a link rel="stylesheet"
        #if tag.name == "link" and tag.get("rel") == ["stylesheet"]:
        #    href_value = tag.get("href")
        #    if href_value and "http" not in href_value:
        #        tag["href"] = f"/{domain}{href_value}" if not domain.endswith("/") else f"/{domain[:-1]}{href_value}"
        #        print(Fore.CYAN + f"Updated stylesheet href to: {tag['href']}")

    for attr in tags_attributes:
        for t in soup.find_all(attrs={attr: True}):
            if t.name == "img":
                continue
            prepend_to_attribute(t, attr)

    script_tags = soup.find_all('script')
    for script in script_tags:
        if script.string:  # Ensure the script tag has text content
            print(Fore.YELLOW + f"Processing script tag: {script}")
            # Replace http:// and https:// with abc://
            updated_script_content = re.sub(r'https?://', f'/https://', script.string)
            script.string.replace_with(updated_script_content)
            print(Fore.CYAN + f"Updated script content: {updated_script_content}")

            # heuristic to remove all scripts involving the defercontent tag
            if script.string and "defercontent" in script.string:
                print(Fore.RED + "Removing defercontent script tag")
                script.decompose()

    modified_html = str(soup)
    # print(Fore.GREEN + "Modified HTML:", modified_html)
    return modified_html


# ------- #
# Caching #
# ------- #

# Define the temporary directory for caching
cache_dir = tempfile.gettempdir() if args.persistent_cache and not args.no_persistent_cache else tempfile.mkdtemp()
print(Fore.GREEN + "Cache Dir:", cache_dir)

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


def get_parent_request_from_cache(url):
    """Get the cached response for a URL-only request."""
    parent_cache_key = f"{url}+{{}}"  # Empty JSON object as string
    return load_cached(parent_cache_key)

def get_parent_request_without_key(url, additional_data, key):
    """Get the cached response for a URL-only request without a specific key."""
    if key in additional_data:
        del additional_data[key]
    additional_data_str_without_key = json.dumps(additional_data, sort_keys=True)
    parent_cache_key = f"{url}+{additional_data_str_without_key}"
    return load_cached(parent_cache_key)[0], additional_data_str_without_key


# ------------ #
# Flask Server #
# ------------ #

app = Flask(__name__)

@app.route("/inject_script.js")
def inject_script():
    if args.dev:
        with open(args.inject_script, "r", encoding="utf-8") as file:
            inject_script_content = file.read()
        return inject_script_content, 200, {'Content-Type': 'application/javascript'}
    return INJECT_SCRIPT, 200, {'Content-Type': 'application/javascript'}

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
        domain, url = url, "" # important: do not change

    if url.endswith(".css/"):
        url = url[:-1]

    # show index
    if path == "":
        return INDEX_HTML, 200, {"Content-Type": "text/html"}

    # reconstruct the "virtual" URL
    full_url = f"{domain}/{url}"
    print(Fore.CYAN + f"DOMAIN/URL={domain}/{url}", "FULL_URL", full_url)

    # Handle different request content types
    content_type = request.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        additional_data = request.get_json() or {}
    else:
        additional_data = request.form.to_dict() or {}

    additional_data_str = json.dumps(additional_data, sort_keys=True)
    cache_key = f"{full_url}+{additional_data_str}"
    unescaped_full_url = urllib.parse.unquote(full_url)
    
    # Check for parent request if additional data exists
    parent_content = None
    if additional_data:
        parent_content, _ = get_parent_request_from_cache(full_url)
        parent_request = json.dumps({"url": full_url })
    
    # Include parent request in the user request if available
    user_request_data = {"url": unescaped_full_url, **additional_data}
    if "get-only-these-css-selectors" in additional_data:
        css_parent_content, css_parent_request = get_parent_request_without_key(full_url, additional_data.copy(), "get-only-these-css-selectors")
    else:
        css_parent_request = None

    user_request = json.dumps(user_request_data, ensure_ascii=False)
    if css_parent_request and parent_content:
        print(Fore.BLUE + "User requested css with parent knowledge:", user_request)
    elif parent_content:
        print(Fore.BLUE + "User requested with parent knowledge:", user_request)
    else:
        print(Fore.BLUE + "User requested:", user_request)

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
    if ".css" in full_url or css_parent_request:
        content_type = "text/css"

    # fill in data into prompt
    #   - OPTIONAL_DATA -> POST request data (for forms, etc.)
    #   - URL_PATH -> virtual url
    #   - FILE_TYPE -> content_type
    print(Fore.MAGENTA + "For request:", user_request)
    print(Fore.MAGENTA + "content-type", content_type)
    prompt_used = CSS_PROMPT if "css" in content_type else BASE_PROMPT
    prompt = prompt_used
    prompt = prompt.replace("{{URL_PATH}}", full_url)
    prompt = prompt.replace("{{FILE_TYPE}}", content_type)

    # api call


    # retry request 3 times
    for i in range(3):
        response = client.chat.completions.create(
            model=args.model_name,
            messages=[
                {"role": "system", "content": prompt},
                # {"role": "user", "content": parent_request},
                # {"role": "system", "content": parent_content},
                {"role": "user", "content": css_parent_request},
                {"role": "system", "content": css_parent_content},
                {"role": "user", "content": user_request}
            ] if parent_content and css_parent_request else [
                {"role": "system", "content": prompt},
                {"role": "user", "content": parent_request},
                {"role": "system", "content": parent_content},
                {"role": "user", "content": user_request}
            ] if parent_content else [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_request}
            ],
            temperature=0.0,
            # max_tokens=4096,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
        if response.choices is not None:
            break
    if response.choices is None:
        return f"ERROR: No response from the AI for the request: {user_request}", 500, {}
    response_data = response.choices[0].message.content

    # remove code block ticks
    response_data = extract_first_code_block(response_data)

    # silently remap all links to proxy-links (we want to keep the user in the AI web)
    try:
	    response_data = prepend_current_domain(response_data, domain+"/")
    except Exception as e:
        print(Fore.RED + "error", str(e))
        pass

    print(Fore.GREEN + content_type)
    print(Fore.GREEN + response_data)

    # unescape in case of javascript files
    if content_type in ["text/javascript", "text/css"]:
        response_data = html.unescape(response_data)

    # Add loadAllSections script before closing body tag
    if content_type == "text/html":
        response_data = response_data.replace(
            "</body>",
            '<script src="/inject_script.js"></script></body>'
        )

    # save cache
    save_cached(cache_key, response_data, content_type)

    return response_data, 200, {'Content-Type': content_type}



if __name__ == "__main__":
    app.run()
