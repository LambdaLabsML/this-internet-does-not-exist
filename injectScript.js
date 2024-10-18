
window.loadedUrls = window.loadedUrls || new Set();

window.loadAllSections = window.loadAllSections || (() => {
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
            const structure = element.getAttribute('structure') || false;

            if (structure) {
                const standardTags = ['div', 'span', 'p'];
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                const urlParts = dynamicUrl.split("/");
                const lastEmptyIndex = urlParts.lastIndexOf("");
                const url = urlParts[lastEmptyIndex + 1];
                const tagName = element.tagName.toLowerCase();
                const isStandardTag = standardTags.includes(tagName)
                const styleFileName = isStandardTag ? 'style.css' : `${tagName}.css`;
                const fullUrl = `/${url}/${styleFileName}`;
                fetchOptions.body.structure = (isStandardTag ? "" : tagName + ">") + structure;

                if (!window.loadedUrls.has(fullUrl)) {
                    window.loadedUrls.add(fullUrl);
                    link.href = fullUrl;
                    document.head.appendChild(link);
                } else {
                    console.log(`style already loaded: ${fullUrl}`);
                }
            }

            if (!window.loadedUrls.has(dynamicUrl)) {
                window.loadedUrls.add(dynamicUrl);
            } else {
                console.log(`content already loaded: ${fullUrl}`);
                return;
            }

            element.innerHTML = '<span style="display:inline-block; opacity:0.5;">Loading content...</span>';
            fetch(dynamicUrl, fetchOptions)
                .then(res => res.text())
                .then(html => {
                    // option 1: replace element with dynamic html
                    //const tempContainer = document.createElement('div');
                    //tempContainer.innerHTML = html;
                    //element.replaceWith(...tempContainer.childNodes);

                    // option 2: insert dynamic html into element
                    element.innerHTML = html;

                    // Extract all script tags
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

window.observer = window.observer || new MutationObserver((mutations) => {
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