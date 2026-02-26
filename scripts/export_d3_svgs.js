/**
 * Export D3 HTML visualizations as standalone SVG files.
 *
 * Uses Puppeteer to render each HTML file in a headless browser,
 * waits for D3 animations to complete, inlines computed styles,
 * and saves the resulting SVG.
 *
 * Usage: node scripts/export_d3_svgs.js
 */
const puppeteer = require("puppeteer");
const path = require("path");
const fs = require("fs");

const BASE = path.resolve(__dirname, "..", "artifacts", "imgs");

const files = [
  { html: "arbitration_timeline.html", svg: "arbitration_timeline.svg" },
  { html: "recurring_arbitration_timeline.html", svg: "recurring_arbitration_timeline.svg" },
  { html: "recurring_editor_disputes.html", svg: "recurring_editor_disputes.svg" },
];

(async () => {
  const browser = await puppeteer.launch({ headless: true });

  for (const { html, svg: svgName } of files) {
    const htmlPath = path.join(BASE, html);
    if (!fs.existsSync(htmlPath)) {
      console.warn(`Skipping ${html} — not found`);
      continue;
    }

    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 900 });
    await page.goto(`file://${htmlPath}`, { waitUntil: "networkidle0" });

    // Wait for D3 animations to finish (longest is ~2s)
    await new Promise((r) => setTimeout(r, 3000));

    // Extract SVG with inlined styles and add background + title
    const svgContent = await page.evaluate(() => {
      const svgEl = document.querySelector("svg");
      if (!svgEl) return null;

      // Get title and subtitle for embedding in SVG
      const titleEl = document.querySelector("h1");
      const subtitleEl = document.querySelector(".subtitle");
      const title = titleEl ? titleEl.textContent : "";
      const subtitle = subtitleEl ? subtitleEl.textContent.trim() : "";

      // Inline computed styles on every element inside the SVG
      function inlineStyles(el) {
        if (el.nodeType !== 1) return; // Element nodes only
        const computed = window.getComputedStyle(el);
        const dominated = [
          "fill",
          "stroke",
          "stroke-width",
          "stroke-dasharray",
          "font-family",
          "font-size",
          "font-weight",
          "text-anchor",
          "opacity",
          "dominant-baseline",
        ];
        for (const prop of dominated) {
          const val = computed.getPropertyValue(prop);
          if (val && val !== "none" && val !== "normal" && val !== "") {
            el.style.setProperty(prop, val);
          }
        }
        for (const child of el.children) {
          inlineStyles(child);
        }
      }

      inlineStyles(svgEl);

      // Get current SVG dimensions
      const w = svgEl.getAttribute("width") || svgEl.getBoundingClientRect().width;
      const h = svgEl.getAttribute("height") || svgEl.getBoundingClientRect().height;

      // Header height for title + subtitle
      const headerH = subtitle ? 70 : 45;
      const padding = 30;
      const totalW = parseFloat(w) + padding * 2;
      const totalH = parseFloat(h) + headerH + padding * 2;

      // Build wrapper SVG with background, title, and the chart
      let wrapper = `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}">`;
      wrapper += `\n  <rect width="100%" height="100%" fill="#0d1117"/>`;

      // Title
      wrapper += `\n  <text x="${padding}" y="${padding + 22}" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:22px;font-weight:600;fill:#e6edf3;">${title}</text>`;

      // Subtitle
      if (subtitle) {
        // Word-wrap subtitle into lines of ~100 chars
        const words = subtitle.split(/\s+/);
        let lines = [];
        let curr = "";
        for (const w of words) {
          if ((curr + " " + w).length > 110 && curr) {
            lines.push(curr);
            curr = w;
          } else {
            curr = curr ? curr + " " + w : w;
          }
        }
        if (curr) lines.push(curr);

        lines.forEach((line, i) => {
          wrapper += `\n  <text x="${padding}" y="${padding + 42 + i * 16}" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:13px;fill:#8b949e;">${line}</text>`;
        });
      }

      // Embed original SVG content offset below header
      const inner = svgEl.innerHTML;
      wrapper += `\n  <g transform="translate(${padding},${headerH + padding})">`;
      wrapper += inner;
      wrapper += `\n  </g>`;
      wrapper += `\n</svg>`;

      return wrapper;
    });

    if (!svgContent) {
      console.warn(`No SVG found in ${html}`);
      await page.close();
      continue;
    }

    const outPath = path.join(BASE, svgName);
    fs.writeFileSync(outPath, svgContent, "utf-8");
    console.log(`✓ ${svgName} (${(svgContent.length / 1024).toFixed(1)} KB)`);

    await page.close();
  }

  await browser.close();
  console.log("\nDone — SVGs saved to artifacts/imgs/");
})();
