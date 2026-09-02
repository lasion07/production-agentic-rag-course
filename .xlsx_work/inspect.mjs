import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
import fs from 'node:fs/promises';

const referencePath = '/Users/lasion/Documents/occupation/NLWeb_core/docs/plan/display_agent_090726/rag_main_supportive_delivery_plan.xlsx';
const targetPath = '/Users/lasion/Documents/occupation/NLWeb_core/docs/plan/display_agent_090726/RAG_Main_Supportive_Backlog_Estimate_AI_Engineer.xlsx';
const outDir = '/Users/lasion/Documents/occupation/production-agentic-rag-course/outputs/rag_plan_update';
await fs.mkdir(outDir, { recursive: true });

async function loadBook(path) {
  const blob = await FileBlob.load(path);
  return SpreadsheetFile.importXlsx(blob);
}

async function summarize(label, book) {
  console.log(`\n===== ${label} =====`);
  console.log((await book.inspect({ kind: 'workbook,sheet,table,definedName', maxChars: 12000, tableMaxRows: 8, tableMaxCols: 12 })).ndjson);
  const sheets = book.worksheets.items;
  for (const sheet of sheets) {
    const used = sheet.getUsedRange();
    console.log(`\n--- SHEET ${sheet.name} ---`);
    console.log((await book.inspect({ kind: 'region', sheetId: sheet.name, range: used.address ?? 'A1:Z50', maxChars: 18000, tableMaxRows: 50, tableMaxCols: 30, tableMaxCellChars: 200 })).ndjson);
    console.log('FORMULAS');
    console.log((await book.inspect({ kind: 'formula', sheetId: sheet.name, range: used.address ?? 'A1:Z50', maxChars: 12000, options: { maxResults: 200 } })).ndjson);
    console.log('STYLES');
    console.log((await book.inspect({ kind: 'computedStyle', sheetId: sheet.name, range: 'A1:Z15', maxChars: 8000 })).ndjson);
    const preview = await book.render({ sheetName: sheet.name, autoCrop: 'all', scale: 1, format: 'png' });
    await fs.writeFile(`${outDir}/${label.replaceAll(' ', '_')}_${sheet.name.replaceAll(' ', '_')}.png`, new Uint8Array(await preview.arrayBuffer()));
  }
}

const reference = await loadBook(referencePath);
const target = await loadBook(targetPath);
await summarize('REFERENCE', reference);
await summarize('TARGET', target);
