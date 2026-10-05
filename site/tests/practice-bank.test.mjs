import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve('site/reference/ecg-id/practice');

test('bundled LUDB practice bank contains six physical-mV real ECGs with hidden expert references', async () => {
  const manifest = JSON.parse(await fs.readFile(path.join(root,'practice_manifest.json'),'utf8'));
  assert.equal(manifest.records.length, 6);
  assert.equal(manifest.doi, '10.13026/eegm-h675');
  assert.match(manifest.license, /Attribution/);

  for (const item of manifest.records) {
    const record = JSON.parse(await fs.readFile(path.join(root,item.file),'utf8'));
    assert.equal(record.sampling_rate_hz, 500);
    assert.equal(record.sample_count, 5000);
    assert.equal(record.units[0], 'mV');
    assert.ok(Number.isFinite(record.recommended_baseline_mV));
    assert.ok(record.annotations.some(a => a.symbol === '(' && a.wave === 'P'));
    assert.ok(record.annotations.some(a => a.symbol === '(' && a.wave === 'QRS'));
    assert.ok(record.annotations.some(a => a.symbol === '(' && a.wave === 'T'));
  }
});
