import { writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const API_URL =
    "https://script.google.com/macros/s/AKfycbywALVBKpOx6icnde7WdZAGPT8GK-OFIS2-Fm1YLO09NNDpLXLjisWUP3J9zKIizbBt/exec";

async function main() {
    console.log("Fetching bulletin data from Apps Script...");
    const res = await fetch(`${API_URL}?action=export_all`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const payload = await res.json();

  const { weeks, data } = payload;
    if (!weeks || !data) throw new Error("Invalid response: missing weeks or data");

  const outDir = join(__dirname, "..", "bulletin", "data");
    mkdirSync(outDir, { recursive: true });

  // index.json - 주차 목록
  const indexPath = join(outDir, "index.json");
    writeFileSync(indexPath, JSON.stringify(weeks, null, 2), "utf8");
    console.log(`Written: bulletin/data/index.json (${weeks.length} weeks)`);

  // 주차별 JSON 파일
  for (const [weekId, weekData] of Object.entries(data)) {
        const filePath = join(outDir, `${weekId}.json`);
        writeFileSync(filePath, JSON.stringify(weekData, null, 2), "utf8");
        console.log(`Written: bulletin/data/${weekId}.json`);
  }

  console.log("Done!");
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
