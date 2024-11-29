// Initialize a dictionary to keep track of loaded URLs and their status
window.loadedUrls = window.loadedUrls || {};
window.showLoaded = window.showLoaded || false;
window.deferredCssSelectors = window.deferredCssSelectors || new Set();

// Helper function to convert FormData to a plain object
function formDataToObject(formData) {
    const obj = {};
    formData.forEach((value, key) => {
        obj[key] = value;
    });
    return obj;
}

// Function to load sections with 'defercontent' tag within a specific node
window.loadAllSections = window.loadAllSections || ((node) => {
    const elements = node ? [node, ...node.querySelectorAll('defercontent')] : document.querySelectorAll('defercontent');
    elements.forEach(element => {
        // Create JSON data from element attributes
        const jsonData = {};
        Array.from(element.attributes).forEach(attr => {
            jsonData[attr.name] = attr.value;
        });

        let dynamicUrl = window.location.href;
        const urlParts = dynamicUrl.split('/');
        if (!dynamicUrl.startsWith("/") && urlParts.length > 3) {
            dynamicUrl = '/' + urlParts.slice(3).join('/');
        }
        const cacheKey = `${dynamicUrl}+options=${JSON.stringify(jsonData)}`;

        // Skip if URL is already loaded or in process
        if (window.loadedUrls[cacheKey]) return;

        window.loadedUrls[cacheKey] = 'loading';
        updateRealTimeBox();

        const fetchOptions = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(jsonData)
        };

        // Handle other tags
        const structure = element.getAttribute('structure') || false;

        // Handle structure loading for non-style tags
        /*
        if (structure && structure !== 'style') {
            if (!window.deferredCssSelectors.has(structure)) {
                const styleDeferContent = document.createElement('defercontent');
                styleDeferContent.setAttribute('query', 'pagestyle');
                styleDeferContent.setAttribute('structure', 'style');
                styleDeferContent.setAttribute('get-only-these-css-selectors', structure);
                document.head.appendChild(styleDeferContent);
                loadAllSections(styleDeferContent);
                window.deferredCssSelectors.add(structure);
            }
        }*/

        // Display loading message
        element.innerHTML = '<span style="display:inline-block; opacity:0.5;">Loading content...</span>';
        fetch(dynamicUrl, fetchOptions)
            .then(res => res.text())
            .then(html => {
                const tempContainer = document.createElement('div');
                tempContainer.innerHTML = html;
                
                // Check if response is a single style element
                if (tempContainer.children.length === 1 && tempContainer.firstElementChild.tagName.toLowerCase() === 'style') {
                    const styleElement = tempContainer.firstElementChild;
                    document.head.appendChild(styleElement);
                    element.remove();
                } else {
                    // Option 1: replace element with dynamic HTML
                    element.replaceWith(...tempContainer.childNodes);
                }

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
                window.loadedUrls[cacheKey] = 'loaded';
                updateRealTimeBox(); // Update real-time box after loading
            })
            .catch(error => {
                console.error(error);
                window.loadedUrls[cacheKey] = 'error';
                updateRealTimeBox();
            });
    });
});

// Function to update the real-time box with URLs not yet loaded and cache keys with their status
function updateRealTimeBox() {
    const box = document.getElementById('realTimeBox');
    if (!box) return;

    const deferContentStatus = Object.entries(window.loadedUrls)
        .filter(([key, status]) => window.showLoaded || status !== 'loaded')
        .map(([key, status]) => {
            let color;
            switch (status) {
                case 'loading':
                    color = 'orange';
                    break;
                case 'loaded':
                    color = 'lightgreen';
                    break;
                case 'error':
                    color = 'red';
                    break;
                default:
                    color = 'white';
            }
            return `<div style="color:${color};">${key} : ${status}</div>`;
        });

    box.innerHTML = `
        <strong>Cache Keys:</strong><br>
        ${deferContentStatus.join('<br>')}
    `;

    // Automatically collapse the box to 100px when all keys are loaded
    const allLoaded = Object.values(window.loadedUrls).every(status => status === 'loaded');
    if (allLoaded && window.showLoaded) {
        box.style.width = '80%';
    } else {
        box.style.width = '100px';
    }
}

// Create and style the real-time box
function createRealTimeBox() {
    const box = document.createElement('div');
    box.id = 'realTimeBox';
    box.style.position = 'fixed';
    box.style.bottom = '0';
    box.style.right = '0';
    box.style.width = '80%'; // Increased width from 300px to 400px
    box.style.maxHeight = '200px';
    box.style.overflowY = 'auto';
    box.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
    box.style.color = 'white';
    box.style.padding = '10px';
    box.style.fontSize = '14px';
    box.style.zIndex = '1000';
    box.style.display = 'block';
    box.style.cursor = 'pointer';
    box.style.borderRadius = '5px';
    box.style.boxShadow = '0 0 10px rgba(0, 0, 0, 0.5)';

    box.onclick = () => {
        window.showLoaded = !window.showLoaded;
        box.style.width = !window.showLoaded ? '100px' : '80%';
        updateRealTimeBox();
    };

    const toggleButton = document.createElement('button');
    toggleButton.textContent = 'Show/Hide URLs';
    toggleButton.style.position = 'absolute';
    toggleButton.style.top = '-30px';
    toggleButton.style.right = '0';
    toggleButton.style.zIndex = '1001';
    toggleButton.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
    toggleButton.style.color = 'white';
    toggleButton.style.border = 'none';
    toggleButton.style.padding = '5px 10px';
    toggleButton.style.cursor = 'pointer';
    toggleButton.style.borderRadius = '5px';

    document.body.appendChild(toggleButton);
    document.body.appendChild(box);
}

// MutationObserver to detect added nodes and load sections if necessary
window.observer = window.observer || new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === 1) { // Check if the node is an element
                    // Check the node itself if it's a 'defercontent' tag
                    if (node.tagName.toLowerCase() === 'defercontent') {
                        loadAllSections(node);
                        updateRealTimeBox();
                    }
                    // Check within the subtree of the node for any 'defercontent' tags
                    node.querySelectorAll('defercontent').forEach(subNode => {
                        loadAllSections(node);
                        updateRealTimeBox();
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
        createRealTimeBox();
        updateRealTimeBox();
        loadAllSections();
    });
}