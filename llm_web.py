import os
import json
from bs4 import BeautifulSoup
from flask import Flask, request
from openai import OpenAI

client = OpenAI()

# flask --app main --debug run

# replace with your own openai key

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Required for session management


BASE_PROMPT = """You are the internet, an expansive and ever-evolving network of interconnected computers, servers, and devices. You house a vast repository of information, entertainment, communication platforms, and services accessible to users worldwide. You facilitate instantaneous sharing and retrieval of data, enabling global connectivity and collaboration. Your infrastructure supports websites, social media, email, cloud computing, streaming services, online commerce, and countless other applications. As the internet, you are the backbone of modern digital life, constantly growing, adapting, and shaping the way people interact with technology and each other.

The user has requested the following URL path: 
    `{{URL_PATH}}`

Respond with the {{FILE_TYPE}}-file that matches the URL.
The first line is the Content-Type of the response.
The following lines is the returned data.
In case of a html response, add relative href links with to related topics.
{{OPTIONAL_DATA}}

Rules:
1. Do not use Markdown Code Blocks. ALWAYS return the website html as plain text.
3. Always inline CSS and (if needed) JS methods to reflect the given URL path.
4. Always provide dense content. Prioritizes rich and dense content and enrich text paragraphs with vast information.
5. Provide links, rabbit-holes and a human touch to emphasize immersion.
"""

def get_file_type(url):
    if "/" not in url or url.endswith("/"):
        return "html"
    _, file_extension = os.path.splitext(url)
    file_type = file_extension.lstrip('.')
    return file_type or "html"


def prepend_current_domain(html_string, domain=""):
    soup = BeautifulSoup(html_string, 'html.parser')
    tags_attributes = {'a': 'href', 'link': 'href', 'script': 'src', 'form': 'action'}

    def prepend_to_attribute(tag, attribute):
        value = tag.get(attribute)
        if value and not value.startswith("#"):
            tag[attribute] = f"/{domain}{value}" if value.startswith("/") and domain != "/" else f"/{value}"

    for tag, attr in tags_attributes.items():
        for t in soup.find_all(tag, **{attr: True}):
            prepend_to_attribute(t, attr)

    return str(soup)




@app.route("/", methods = ['POST', 'GET'])
@app.route("/<path:path>", methods = ['POST', 'GET'])
def catch_all(path=""):
    print(request.url)
    url = request.url.replace("http://localhost:5000/","")
    if "/" in url:
        domain, url = url.split("/", 1)
    else:
        domain, url = url, ""

    if "favicon.ico" in request.url:
        return "", 200, {}

    # is this a POST request with data?
    if request.form:
        prompt = BASE_PROMPT.replace("{{OPTIONAL_DATA}}", f"form data: {json.dumps(request.form)}")
    else:
        prompt = BASE_PROMPT
    full_url = f"{domain}/{url}"
    print(f"DOMAIN/URL={domain}/{url}")
    prompt = prompt.replace("{{URL_PATH}}", full_url)
    prompt = prompt.replace("{{FILE_TYPE}}", "HTML")

    #model="gpt-4-turbo"
    #model="gpt-3.5-turbo"
    model="gpt-4o"
    response = client.chat.completions.create(model=model,
    messages=[{"role": "system", "content": prompt}],
    temperature=0.0,
    max_tokens=4096,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0)

    ai_data = response.choices[0].message.content
    content_type = ai_data.splitlines()[0]
    response_data = "\n".join(ai_data.splitlines()[1:])
    try:
	    return prepend_current_domain(response_data, domain+"/"), 200, {'Content-Type': content_type}
    except Exception as e:    
	    return response_data, 200, {'Content-Type': content_type}
