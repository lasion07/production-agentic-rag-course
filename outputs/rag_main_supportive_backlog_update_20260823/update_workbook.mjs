import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const mode = process.argv[2] ?? "inspect";
const sourceDir = "/Users/lasion/Documents/occupation/NLWeb_core/docs/plan/display_agent_090726";
const targetPath = path.join(sourceDir, "RAG_Main_Supportive_Backlog_Estimate_AI_Engineer.xlsx");
const referencePath = path.join(sourceDir, "rag_main_supportive_delivery_plan.xlsx");
const outputDir = "/Users/lasion/Documents/occupation/production-agentic-rag-course/outputs/rag_main_supportive_backlog_update_20260823";
const outputPath = path.join(outputDir, "RAG_Main_Supportive_Backlog_Estimate_AI_Engineer_updated.xlsx");

async function loadWorkbook(filePath) {
  return SpreadsheetFile.importXlsx(await FileBlob.load(filePath));
}

async function inspectWorkbook(label, workbook) {
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table,drawing",
    maxChars: 12000,
    tableMaxRows: 15,
    tableMaxCols: 18,
    tableMaxCellChars: 160,
  });
  console.log(`--- ${label} SUMMARY ---`);
  console.log(summary.ndjson);

  const sheets = (await workbook.inspect({ kind: "sheet", include: "id,name" })).ndjson
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .map((item) => item.name)
    .filter(Boolean);
  for (const sheetName of sheets) {
    const region = await workbook.inspect({
      kind: "region,computedStyle",
      sheetId: sheetName,
      range: "A1:Z60",
      maxChars: 9000,
      tableMaxRows: 60,
      tableMaxCols: 26,
      tableMaxCellChars: 180,
    });
    console.log(`--- ${label} ${sheetName} REGION ---`);
    console.log(region.ndjson);
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
    const safeName = sheetName.replace(/[^a-z0-9_-]+/gi, "_");
    await fs.writeFile(path.join(outputDir, `${label}_${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}

if (mode === "inspect") {
  await fs.mkdir(outputDir, { recursive: true });
  await inspectWorkbook("target", await loadWorkbook(targetPath));
  await inspectWorkbook("reference", await loadWorkbook(referencePath));
  process.exit(0);
}

if (mode !== "edit") {
  throw new Error(`Unsupported mode: ${mode}`);
}

// Editing logic is added after the inspection pass so it can match the source workbooks.
const workbook = await loadWorkbook(targetPath);
await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
