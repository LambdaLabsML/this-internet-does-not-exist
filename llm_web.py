# Use: flask --app main --debug run

import html
import hashlib
import json
import mimetypes
import os
import re
import tempfile
from bs4 import BeautifulSoup
from flask import Flask, request
from openai import OpenAI


BASE_URL = "http://localhost:5000/"
API_URL = None
API_KEY = None
PERSISTENT_CACHE = True
MODEL_NAME = "gpt-4o"
with open("base_prompt.txt", "r") as file:
    BASE_PROMPT = file.read()
with open("index.html", "r") as file:
    INDEX_HTML = file.read()


# ------ #
# Helper #
# ------ #

def prepend_current_domain(html_string, domain=""):
    soup = BeautifulSoup(html_string, 'html.parser')
    tags_attributes = ['href', 'src', 'action', 'data-url']

    def prepend_to_attribute(tag, attribute):
        value = tag.get(attribute)
        if value and not value.startswith("#"):
            if value.startswith("/"):
                tag[attribute] = f"/{domain}{value}" if domain != "/" else f"{value}"
            else:
                tag[attribute] = f"/{value}"

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

    return str(soup)


# ------- #
# Caching #
# ------- #

# Define the temporary directory for caching
cache_dir = tempfile.gettempdir() if PERSISTENT_CACHE else tempfile.mkdtemp()
print("Cache Dir:", cache_dir)

def _get_cache_file_path(url):
    # Generate a unique filename based on the URL hash
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    return os.path.join(cache_dir, f"{url_hash}.cache")

def load_cached(url):
    cache_file_path = _get_cache_file_path(url)
    if os.path.exists(cache_file_path):
        with open(cache_file_path, 'r') as cache_file:
            cached_data = json.load(cache_file)
            return cached_data.get('content'), cached_data.get('content_type')
    return None, None

def save_cached(url, content, content_type):
    cache_file_path = _get_cache_file_path(url)
    cache_data = {
        'content': content,
        'content_type': content_type
    }
    with open(cache_file_path, 'w') as cache_file:
        json.dump(cache_data, cache_file)



# ------------ #
# Flask Server #
# ------------ #

client = OpenAI(api_key=API_KEY, base_url=API_URL)
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

    # show index
    print(domain, url)
    if path == "":
        return INDEX_HTML, 200, {"Content-Type": "text/html"}

    # reconstruct the "virtual" URL
    full_url = f"{domain}/{url}"
    print(f"DOMAIN/URL={domain}/{url}")

    # use cache
    cached, content_type = load_cached(full_url)
    if cached:
        return cached, 200, {"Content-Type": content_type}

    # skip favicon creation
    if "favicon.ico" in request.url:
        return "", 200, {}

    # get content type
    content_type, _ = mimetypes.guess_type(url.split("?")[0])
    if content_type is None:
        content_type = 'text/html'

    # fill in data into prompt
    #   - OPTIONAL_DATA -> POST request data (for forms, etc.)
    #   - URL_PATH -> virtual url
    #   - FILE_TYPE -> content_type
    prompt = BASE_PROMPT if not request.form else BASE_PROMPT.replace("{{OPTIONAL_DATA}}", f"\nForm data: {json.dumps(request.form)}")
    prompt = prompt.replace("{{URL_PATH}}", full_url)
    prompt = prompt.replace("{{FILE_TYPE}}", content_type)

    # api call
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": full_url}],
        temperature=0.0,
        max_tokens=4096,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    response_data = response.choices[0].message.content

    # silently remap all links to proxy-links (we want to keep the user in the AI web)
    try:
	    response_data = prepend_current_domain(response_data, domain+"/")
    except Exception as e:
        print("error", str(e))
        pass

    print(content_type)
    print(response_data)


    # unescape in case of javascript files
    if content_type == "text/javascript":
        response_data = html.unescape(response_data)

    # save cache
    save_cached(full_url, response_data, content_type)

    return response_data, 200, {'Content-Type': content_type}
