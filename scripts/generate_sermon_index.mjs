{\rtf1\ansi\ansicpg949\cocoartf2639
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;\f1\fnil\fcharset129 AppleSDGothicNeo-Regular;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx566\tx1133\tx1700\tx2267\tx2834\tx3401\tx3968\tx4535\tx5102\tx5669\tx6236\tx6803\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import fs from "fs";\
import path from "path";\
\
const TEXT_DIR = path.join(process.cwd(), "sermon", "texts");\
const OUT_FILE = path.join(TEXT_DIR, "index.json");\
\
function main() \{\
  if (!fs.existsSync(TEXT_DIR)) \{\
    console.error("Folder not found:", TEXT_DIR);\
    process.exit(1);\
  \}\
\
  const files = fs.readdirSync(TEXT_DIR)\
    .filter((n) => /\\.txt$/i.test(n))\
    .sort((a, b) => b.localeCompare(a)); // 
\f1 \'c3\'d6\'bd\'c5
\f0  
\f1 \'b3\'af\'c2\'a5\'b0\'a1
\f0  
\f1 \'c0\'a7\'b7\'ce
\f0 \
\
  fs.writeFileSync(OUT_FILE, JSON.stringify(\{ files \}, null, 2) + "\\n", "utf8");\
  console.log(`Generated index.json with $\{files.length\} files`);\
\}\
\
main();\
}