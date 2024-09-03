from flask import Flask, request
import os
from openai import OpenAI

client = OpenAI()
import json

# flask --app main --debug run

# replace with your own openai key

app = Flask(__name__)


BASE_PROMPT = """Create a response document with content that matches the following URL path: 
    `{{URL_PATH}}`

The first line is the Content-Type of the response.
The following lines is the returned data.
In case of a html response, add relative href links with to related topics.
{{OPTIONAL_DATA}}

Content-Type:
"""

#2. embed only small images as base64 png right in the single-file html site

import random
import nltk
nltk.download('words')
from nltk.corpus import words

@app.route("/", methods = ['POST', 'GET'])
@app.route("/<path:path>", methods = ['POST', 'GET'])
def catch_all(path=""):

    # is this a POST request with data?
    if request.form:
        prompt = BASE_PROMPT.replace("{{OPTIONAL_DATA}}", f"form data: {json.dumps(request.form)}")
    else:
        prompt = BASE_PROMPT.replace("{{OPTIONAL_DATA}}", f"Use these random words to kickstart your creativity and increase number of words of the output overall: "+str([random.choice(words.words()) for _ in range(100)]))
    print("URL=",path)
    print(prompt)
    prompt = prompt.replace("{{URL_PATH}}", path)

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

    print(ai_data)

    content_type = ai_data.splitlines()[0]
    response_data = "\n".join(ai_data.splitlines()[1:])
    return response_data, 200, {'Content-Type': content_type}
