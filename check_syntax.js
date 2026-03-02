const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;

const html = fs.readFileSync('templates/flock_detail.html', 'utf8');

// Extract script content
const dom = new JSDOM(html);
const scripts = dom.window.document.querySelectorAll('script');

scripts.forEach((script, index) => {
    if (script.textContent.includes('const commonOptions')) {
        console.log(`Checking script block ${index}...`);
        try {
            // Very naive check: just try parsing
            // new Function(script.textContent);
            console.log("Found commonOptions");
            // Find commonOptions specifically
            const match = script.textContent.match(/const commonOptions = \{[\s\S]*?\n  \};\n/);
            if (match) {
                console.log(match[0]);
            }
        } catch (e) {
            console.error(e);
        }
    }
});
