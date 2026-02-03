import fs from "fs";
import path from "path";

const TEXT_DIR = path.join(process.cwd(), "sermon", "texts");
const OUT_FILE = path.join(TEXT_DIR, "index.json");

function main() {
  if (!fs.existsSync(TEXT_DIR)) {
    console.error("Folder not found:", TEXT_DIR);
    process.exit(1);
  }

  const files = fs.readdirSync(TEXT_DIR)
    .filter((n) => /\.txt$/i.test(n))
    .sort((a, b) => b.localeCompare(a)); // 최신 날짜가 위로

  fs.writeFileSync(OUT_FILE, JSON.stringify({ files }, null, 2) + "\n", "utf8");
  console.log(`Generated index.json with ${files.length} files`);
}

main();
