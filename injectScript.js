// Initialize a Set to keep track of loaded URLs
window.loadedUrls = window.loadedUrls || new Set();

// Function to load all sections with 'defercontent' tag
window.loadAllSections = window.loadAllSections || (() => {
    document.querySelectorAll('defercontent').forEach(element => {
        // Skip already processed elements
        if (element.hasAttribute('data-processed')) return;
        element.setAttribute('data-processed', 'true');

        const dynamicUrl = window.location.href;
        console.log(dynamicUrl);
        const tagName = element.tagName.toLowerCase();

        // Prepare POST data from element attributes
        const postData = new FormData();
        Array.from(element.attributes).forEach(attr => {
            if (attr.name !== 'data-processed') {
                postData.append(attr.name, attr.value);
            }
        });

        const fetchOptions = {
            method: 'POST',
            body: postData
        };

        // Handle 'link' tags with rel='stylesheet'
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
            // Handle 'script' tags
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
            // Handle other tags
            const structure = element.getAttribute('structure') || false;

            if (structure) {
                const urlParts = dynamicUrl.split("/");
                const lastEmptyIndex = urlParts.lastIndexOf("");
                const url = urlParts[lastEmptyIndex + 1];
                const fullUrl = `/${url}/style.css`;
                const cacheKey = `${fullUrl}+structure=${structure}+options=${JSON.stringify(fetchOptions)}`;  // Combine URL with serialized fetch options

                // Check if the cache key (including fetchOptions) exists in window.loadedUrls
                if (!window.loadedUrls.has(cacheKey)) {
                    window.loadedUrls.add(cacheKey);

                    // Use fetch() to make a POST request (with additional parameters) to fetch the CSS
                    fetch(fullUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded'
                        },
                        body: structure  // Send the structure as raw text
                    })
                        .then(response => {
                            if (!response.ok) { throw new Error(`Failed to load stylesheet: ${response.statusText}`); }
                            return response.text(); // Get the response as text (CSS content)
                        })
                        .then(cssContent => {
                            const styleTag = document.createElement('style');
                            styleTag.innerHTML = cssContent;
                            document.head.appendChild(styleTag);
                            console.log(fullUrl, styleTag);
                        })
                        .catch(error => {
                            console.error('Error fetching CSS:', error);
                        });
                } else {
                    console.log(`style already loaded: ${cacheKey}`);
                }
            }

            if (!window.loadedUrls.has(cacheKey)) {
                window.loadedUrls.add(cacheKey);
            } else {
                console.log(`content already loaded: ${cacheKey}`);
                return;
            }

            // Display loading message
            element.innerHTML = '<span style="display:inline-block; opacity:0.5;">Loading content...</span>';
            fetch(dynamicUrl, fetchOptions)
                .then(res => res.text())
                .then(html => {
                    // Option 1: replace element with dynamic HTML
                    const tempContainer = document.createElement('div');
                    tempContainer.innerHTML = html;
                    element.replaceWith(...tempContainer.childNodes);

                    // Option 2: insert defercontent HTML into element
                    // element.innerHTML = html;

                    // Extract and execute all script tags
                    const scripts = element.querySelectorAll('script');
                    scripts.forEach(script => {
                        const newScript = document.createElement('script');
                        if (script.src) {
                            // If the script has a src attribute, copy it and load the external script
                            newScript.src = script.src;
                            newScript.async = true;  // Preserve async behavior
                        } else {
                            // Inline script - copy the content
                            newScript.textContent = script.textContent;
                        }
                        document.body.appendChild(newScript);  // Append script to body to execute
                    });
                })
                .catch(console.error);
        }
    });
});

// MutationObserver to detect added nodes and load sections if necessary
window.observer = window.observer || new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === 1) { // Check if the node is an element
                    // Check the node itself if it's a 'defercontent' tag
                    if (node.tagName.toLowerCase() === 'defercontent') {
                        loadAllSections();
                    }
                    // Check within the subtree of the node for any 'defercontent' tags
                    node.querySelectorAll('defercontent').forEach(subNode => {
                        if (!subNode.hasAttribute('data-processed')) {
                            loadAllSections();
                        }
                    });
                }
            });
        }
    });
});

// Initialize observer and load sections on DOMContentLoaded
if (!window.initalized) {
    window.initalized = true;

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    document.addEventListener("DOMContentLoaded", () => {
        loadAllSections();
    });
}