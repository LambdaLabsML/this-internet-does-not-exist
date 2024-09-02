# Use: flask --app main --debug run

import argparse
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
    return parser.parse_args()

args = parse_arguments()
client = OpenAI(api_key=args.api_key, base_url=args.api_url)
with open(args.base_prompt, "r") as file:
    BASE_PROMPT = file.read()
with open(args.css_prompt, "r") as file:
    CSS_PROMPT = file.read()
with open("index.html", "r") as file:
    INDEX_HTML = file.read()




# ------ #
# Helper #
# ------ #

def prepend_current_domain(html_string, domain=""):
    soup = BeautifulSoup(html_string, 'html.parser')
    tags_attributes = ['href', 'src', 'action', 'data-dynamic-content-url']

    def prepend_to_attribute(tag, attribute):
        value = tag.get(attribute)
        if value and not value.startswith("#"):
            if value.startswith("/"):
                if domain.endswith("/"):
                    tag[attribute] = f"/{domain[:-1]}{value}" if domain != "/" else f"{value}"
                else:
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
cache_dir = tempfile.gettempdir() if args.persistent_cache and not args.no_persistent_cache else tempfile.mkdtemp()
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
    prompt_used = CSS_PROMPT if "css" in content_type else BASE_PROMPT
    prompt = prompt_used
    prompt = prompt.replace("{{URL_PATH}}", full_url)
    prompt = prompt.replace("{{FILE_TYPE}}", content_type)

    # api call
    additional_data = request.form.to_dict() or {}
    user_request = json.dumps({"url": html.unescape(full_url), **additional_data})
    print("User requested:", user_request)
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
            """
            <script>
                const loadAllSections = () => {
                    document.querySelectorAll('[data-dynamic-content-url]').forEach(element => {
                        if (element.hasAttribute('data-processed')) return;
                        element.setAttribute('data-processed', 'true');

                        const dynamicUrl = element.dataset.dynamicContentUrl;
                        const tagName = element.tagName.toLowerCase();

                        const postData = new FormData();
                        Array.from(element.attributes).forEach(attr => {
                            if (attr.name !== 'data-dynamic-content-url' && attr.name !== 'data-processed') {
                                postData.append(attr.name, attr.value)
                            }
                        });

                        const fetchOptions = {
                            method: 'POST',
                            body: postData
                        };

                        if (tagName === 'link' && element.rel === 'stylesheet') {
                            fetch(dynamicUrl, fetchOptions)
                                .then(res => res.text())
                                .then(css => {
                                    const style = document.createElement('style');
                                    style.textContent = css;
                                    document.head.appendChild(style);
                                    element.remove();
                                })
                                .catch(console.error);
                        } else if (tagName === 'script') {
                            fetch(dynamicUrl, fetchOptions)
                                .then(res => res.text())
                                .then(js => {
                                    const script = document.createElement('script');
                                    script.textContent = js;
                                    document.head.appendChild(script);

                                    // Ensure the script is executed immediately after appending it to the head
                                    const clonedScript = document.createElement('script');
                                    clonedScript.type = 'text/javascript';
                                    clonedScript.text = script.text;
                                    document.body.appendChild(clonedScript);

                                    element.remove();
                                })
                                .catch(console.error);
                        } else {
                            const structure = element.getAttribute('data-structure') || false;

                            if (structure) {
                                const link = document.createElement('link');
                                link.rel = 'stylesheet';
                                const urlParts = dynamicUrl.split("/")
                                const lastEmptyIndex = urlParts.lastIndexOf("");
                                const url = urlParts[lastEmptyIndex+1];
                                link.href = `/${url}/style.css?structure=${structure}`;
                                document.head.appendChild(link);
                            }

                            element.innerHTML = '<span style="display:inline-block; opacity:0.5;">Loading content...</span>';
                            fetch(dynamicUrl, fetchOptions)
                                .then(res => res.text())
                                .then(html => {
                                    const tempContainer = document.createElement('div');
                                    tempContainer.innerHTML = html;
                                    element.replaceWith(...tempContainer.childNodes);
                                })
                                .catch(console.error);
                        }
                    });
                };

                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'childList') {
                            mutation.addedNodes.forEach((node) => {
                                if (node.nodeType === 1) { // Check if the node is an element
                                    // Check the node itself
                                    if (node.hasAttribute('data-dynamic-content-url')) {
                                        loadAllSections();
                                    }
                                    // Check within the subtree of the node
                                    node.querySelectorAll('[data-dynamic-content-url]').forEach(subNode => {
                                        if (!subNode.hasAttribute('data-processed')) {
                                            loadAllSections();
                                        }
                                    });
                                }
                            });
                        }
                    });
                });

                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });

                document.addEventListener("DOMContentLoaded", () => {
                    loadAllSections();
                });
            </script>
        </body>
            """
        )

    # save cache
    save_cached(full_url, response_data, content_type)

    return response_data, 200, {'Content-Type': content_type}



if __name__ == "__main__":
    app.run()
