// Execute supplied, retained R expressions using a pinned independent runtime.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import crypto from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
async function replaceCheckpoint(temporary, target) {
    for(let attempt=0; attempt<6; attempt++) {
        try { fs.renameSync(temporary,target); return; }
        catch(error) {
            if(!['EPERM','EACCES','EBUSY'].includes(error.code) || attempt===5) throw error;
            await delay(20*2**attempt);
        }
    }
}
const [queriesFile, outputFile, runtimeRoot] = process.argv.slice(2);
if (!queriesFile || !outputFile || !runtimeRoot) throw new Error('Expected queries, output, runtime root.');
const packageRoot = path.join(runtimeRoot, 'node_modules', 'webr');
const metadata = JSON.parse(fs.readFileSync(path.join(packageRoot, 'package.json')));
if (metadata.version !== '0.6.0') throw new Error('Expected WebR 0.6.0.');
const {WebR} = await import(pathToFileURL(path.join(packageRoot, 'dist', 'webr.mjs')).href);
const webR = new WebR();
await webR.init();
try {
    const version = await webR.evalR('R.version.string');
    const queries = JSON.parse(fs.readFileSync(queriesFile));
    const rows = [];
    const wasmHash = crypto.createHash('sha256').update(fs.readFileSync(path.join(packageRoot, 'dist', 'R.wasm'))).digest('hex');
    const identity = {webR:metadata.version, R:await version.toArray(), node:process.version, wasm_sha256:wasmHash};
    const partialFile = outputFile.replace(/\.json$/, '.partial.json');
    const journalFile = outputFile.replace(/\.json$/, '.progress.jsonl');
    fs.writeFileSync(journalFile, JSON.stringify({identity, requested_queries:queries.length})+'\n');
    for (const query of queries) {
        try {
            const result = await webR.evalR(query.code);
            const values = await result.toArray();
            const nonfinite = values.map(value => Number.isNaN(value) ? 'nan' :
                value === Infinity ? 'positive_infinity' : value === -Infinity ? 'negative_infinity' : null);
            rows.push({...query, values, nonfinite, status:'executed'});
            await webR.destroy(result);
        } catch (error) {
            rows.push({...query, status:'failed', error:String(error)});
        }
        fs.appendFileSync(journalFile, JSON.stringify({index:rows.length-1, row:rows[rows.length-1]})+'\n');
        fs.writeFileSync(partialFile + '.tmp', JSON.stringify({...identity, complete:false, requested_queries:queries.length,
            completed_queries:rows.length, progress_file:journalFile}, null, 2)+'\n');
        await replaceCheckpoint(partialFile + '.tmp', partialFile);
    }
    fs.writeFileSync(outputFile, JSON.stringify({...identity, rows}, null, 2)+'\n');
    console.log(JSON.stringify({queries:rows.length, failures:rows.filter(r=>r.status !== 'executed').length}));
} finally {
    webR.close();
}
