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



BASE_PROMPT = """Respond with the raw {{FILE_TYPE}}-file that matches the URL.
{{OPTIONAL_DATA}}

Rules:
1. ALWAYS return the plain {{FILE_TYPE}}-file directly. Do not use markdown code blocks and do not prepend the file with any comment.
2. Generate a dense and authentic website:
    Structure: Use HTML to reflect clear hierarchy (headings, lists, tables).
    Links: Include extensive internal/external hyperlinks, woven into text whenever appropriate. Use <a class="button" href="..."> to use CTA button/links.
    Styling: Use <link rel="stylesheet" href="URL/style.css?patterns=PATTERNLIST> to load styles dynamically.
    Typography: Match fonts, spacing, layout.
    Interactivity: Implement JS for dropdowns, modals, search.
    Defer Content: Defer content using dynamically loaded content (using <button>Load Content</button>) to optimize speed. Answer only with that part when a url uses the `get_only` parameter. (See Example below)
    Multimedia: Correctly reference and load all media.
    Interactive: Input fields are interactive. Use for instance <form submit="URL/search?..."> to lead the user to search results.
    Colors: Properly chosen colors in elements such as text, headers, backgrounds are key in making website feel real. Choose colors according to real counterparts.
3. 

Example:
Input: en.wikipedia.org/wiki/Obelus
Output: <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Obelus - Wikipedia</title>
    <meta name="description" content="The obelus is a symbol consisting of a line with dots above and below, used historically for division or subtraction.">
    <link rel="stylesheet" href="en.wikipedia.org/style.css?patterns=body,a,a:hover,a.button,header,h1,main,h2,table,th,td,url,footer,.references">
</head>
<body onload="loadAllSections()">
    <header>
        <h1>Obelus</h1>
    </header>

    <main>
        <h2 id="introduction">Introduction</h2>
        <div data-url="https://en.wikipedia.org/wiki/Obelus?get_only=introduction"></div>

        <h2 id="history">History</h2>
        <div data-url="https://en.wikipedia.org/wiki/Obelus?get_only=history"></div>

        <h2 id="modern-use">Modern Use</h2>
        <div data-url="https://en.wikipedia.org/wiki/Obelus?get_only=modern-use"></div>
        
        <h2 id="similar-symbols">Similar Symbols</h2>
        <div data-url="https://en.wikipedia.org/wiki/Obelus?get_only=similar-symbols"></div>

        <h2 id="see-also">See Also</h2>
        <div data-url="https://en.wikipedia.org/wiki/Obelus?get_only=see-also"></div>

        <h2 id="references">References</h2>
        <div data-url="https://en.wikipedia.org/wiki/Obelus?get_only=references"></div>
    </main>

    <footer>
        <p>This article is a concise summary of the topic <a href="https://en.wikipedia.org/wiki/Obelus">Obelus</a> from Wikipedia.</p>
    </footer>

    <script>
        const loadAllSections = () => {
            document.querySelectorAll('div[data-url]').forEach(div => {
                div.innerHTML = '<span style="display:inline-block; opacity:0.5;">Loading content...</span>';
                fetch(div.dataset.url)
                    .then(res => res.text())
                    .then(html => div.outerHTML = html)
                    .catch(console.error);
            });
        };
    </script>
</body>
</html>

Input: en.wikipedia.org/style.css?patterns=body,a,a:hover,header,h1,main,h2,table,th,td,url,footer,.references
Output: body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 0;
    background-color: #f8f9fa;
    color: #202122;
    line-height: 1.6;
}

a {
    color: #0b0080;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

a.button {
    display: inline-block;
    padding: 8px 15px;
    margin: 5px 0;
    font-size: 14px;
    font-weight: bold;
    color: #0645AD;
    background-color: #f8f9fa;
    border: 1px solid #a2a9b1;
    border-radius: 2px;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
}

a.button:hover {
    background-color: #f1f1f1;
    color: #0645AD;
    border-color: #72777d;
}

a.button:active {
    background-color:
    border-color: #72777d;
    color: #0645AD;
}

header {
    background-color: #eaecf0;
    padding: 1rem;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
}

h1 {
    margin: 0;
    font-size: 2rem;
}

main {
    max-width: 800px;
    margin: 1rem auto;
    padding: 0 1rem;
}

h2 {
    margin-top: 2rem;
    border-bottom: 1px solid #a2a9b1;
    padding-bottom: 0.3rem;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1rem;
}

th, td {
    border: 1px solid #a2a9b1;
    padding: 0.5rem;
    text-align: left;
}

th {
    background-color: #f2f2f2;
}

url {
    word-break: break-all;
}

footer {
    background-color: #eaecf0;
    padding: 1rem;
    text-align: center;
    font-size: 0.9rem;
    color: #707070;
}

.references {
    list-style-type: decimal;
    padding-left: 2rem;
}


Input: en.wikipedia.org/Obulus?get_only=introduction
Output: <p>The <strong>obelus</strong> (<a href="https://en.wikipedia.org/wiki/Division_sign">÷</a>) is a symbol consisting of a line with a dot above and a dot below. It is primarily used in <a href="https://en.wikipedia.org/wiki/Mathematics">mathematics</a> to represent <a href="https://en.wikipedia.org/wiki/Division_(mathematics)">division</a> or, less commonly, <a href="https://en.wikipedia.org/wiki/Subtraction">subtraction</a>. The symbol has a rich history that spans from <a href="https://en.wikipedia.org/wiki/Ancient_Greece">Ancient Greece</a> to modern mathematical notation.</p>

Input: en.wikipedia.org/Obulus?get_only=history
Output: <p>The obelus was first introduced by the Greek scholar <a href="https://en.wikipedia.org/wiki/Aristarchus_of_Samos">Aristarchus of Samos</a> in the 3rd century BC, primarily as a textual marker used in <a href="https://en.wikipedia.org/wiki/Ancient_manuscripts">ancient manuscripts</a> to indicate passages that were of dubious authenticity<sup>[1]</sup>. Over time, this symbol evolved in its use. During the Middle Ages, it was adopted by scholars and printers, most notably by the Swiss mathematician <a href="https://en.wikipedia.org/wiki/Johann_Rahn">Johann Rahn</a> in 1659, who repurposed the obelus as a division sign in his work "Teutsche Algebra"<sup>[2]</sup>.</p>
<p>In early mathematical contexts, the obelus was used interchangeably with the colon (:) to represent division. However, its use became standardized as the division symbol in English-speaking countries, while other regions, particularly in Europe, favored the slash (/) or the horizontal line (—) for division<sup>[3]</sup>.</p>


Input: en.wikipedia.org/Obulus?get_only=modern-use
Output: <p>Today, the obelus is primarily used in <a href="https://en.wikipedia.org/wiki/Elementary_arithmetic">elementary arithmetic</a> to denote division. Despite its historical significance, its usage has declined in favor of the slash (/) and the horizontal line, especially in higher mathematics<sup>[4]</sup>. The obelus is also sometimes used to indicate subtraction, though this is rare and largely considered archaic.</p>

<p>The obelus also appears in other contexts, such as in certain programming languages where it may be used to represent division operations. However, these instances are less common, as the majority of modern programming languages prefer the slash for division<sup>[5]</sup>.</p>

Input: en.wikipedia.org/Obulus?get_only=similar-symbols
Output: <p>The obelus is often confused with other symbols used in mathematics and textual notation. The table below highlights some of these similar symbols:</p>

<table>
    <thead>
        <tr>
            <th>Symbol</th>
            <th>Name</th>
            <th>Usage</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>÷</td>
            <td><a href="https://en.wikipedia.org/wiki/Obelus">Obelus</a></td>
            <td>Used to represent division or, rarely, subtraction.</td>
        </tr>
        <tr>
            <td>:</td>
            <td><a href="https://en.wikipedia.org/wiki/Colon_(punctuation)">Colon</a></td>
            <td>Sometimes used as a division sign, especially in European countries.</td>
        </tr>
        <tr>
            <td>/</td>
            <td><a href="https://en.wikipedia.org/wiki/Slash_(punctuation)">Slash</a></td>
            <td>Commonly used as a division symbol in programming and higher mathematics.</td>
        </tr>
        <tr>
            <td>—</td>
            <td><a href="https://en.wikipedia.org/wiki/Vinculum_(symbol)">Vinculum</a></td>
            <td>Used in fractions to separate the numerator and denominator.</td>
        </tr>
        <tr>
            <td>&#43;</td>
            <td><a href="https://en.wikipedia.org/wiki/Plus_sign">Plus Sign</a></td>
            <td>Used to denote addition.</td>
        </tr>
        <tr>
            <td>&#8722;</td>
            <td><a href="https://en.wikipedia.org/wiki/Minus_sign">Minus Sign</a></td>
            <td>Used to denote subtraction.</td>
        </tr>
    </tbody>
</table>


Input: en.wikipedia.org/Obulus?get_only=see-also
Output: <ul>
    <li><a href="https://en.wikipedia.org/wiki/Division_sign">Division sign</a></li>
    <li><a href="https://en.wikipedia.org/wiki/Slash_(punctuation)">Slash (punctuation)</a></li>
    <li><a href="https://en.wikipedia.org/wiki/Solidus_(punctuation)">Solidus (punctuation)</a></li>
    <li><a href="https://en.wikipedia.org/wiki/Multiplication_sign">Multiplication sign</a></li>
    <li><a href="https://en.wikipedia.org/wiki/Minus_sign">Minus sign</a></li>
</ul>

Input: en.wikipedia.org/Obulus?get_only=references
Output: <ol class="references">
    <li><a href="https://en.wikipedia.org/wiki/Aristarchus_of_Samos">Aristarchus of Samos - Wikipedia</a></li>
    <li>Rahn, J. "Teutsche Algebra", Zurich, 1659.</li>
    <li><a href="https://en.wikipedia.org/wiki/History_of_mathematical_symbols">History of Mathematical Symbols - Wikipedia</a></li>
    <li>Smith, A. "Mathematical Notation in the Modern World", Mathematics Journal, 2009.</li>
    <li><a href="https://en.wikipedia.org/wiki/Programming_languages">Programming Languages - Wikipedia</a></li>
</ol>
"""


def prepend_current_domain(html_string, domain=""):
    soup = BeautifulSoup(html_string, 'html.parser')
    tags_attributes = {'a': 'href', 'link': 'href', 'script': 'src', 'form': 'action', 'div': 'data-url'}

    def prepend_to_attribute(tag, attribute):
        value = tag.get(attribute)
        if value and not value.startswith("#"):
            if value.startswith("/"):
                tag[attribute] = f"/{domain}{value}" if domain != "/" else f"{value}"
            else:
                tag[attribute] = f"/{value}"

    for tag, attr in tags_attributes.items():
        for t in soup.find_all(tag, **{attr: True}):
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
        return index_html, 200, {"Content-Type": "text/html"}

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
