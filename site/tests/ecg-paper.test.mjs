import test from "node:test";
import assert from "node:assert/strict";
import {
  ECG_PAPER_TIME_SMALL_BOX_S,
  computeSquarePaperRange,
  pixelsPerVerticalSmallBox
} from "../reference/ecg-id/ecg-paper.mjs";

test("40 ms horizontal and one vertical calibration step occupy equal pixels",()=>{
  const width=1000;
  const height=500;
  const duration=2;
  const verticalStep=0.1;
  const range=computeSquarePaperRange({
    widthPx:width,heightPx:height,visibleDurationSeconds:duration,
    verticalSmallBox:verticalStep,baseline:0,dataMin:-0.3,dataMax:1.0
  });
  const horizontalPx=width*ECG_PAPER_TIME_SMALL_BOX_S/duration;
  const verticalPx=pixelsPerVerticalSmallBox({
    heightPx:height,yMin:range.yMin,yMax:range.yMax,verticalSmallBox:verticalStep
  });
  assert.ok(Math.abs(horizontalPx-verticalPx)<1e-9);
});

test("paper range may shift without changing calibration to keep ECG visible",()=>{
  const range=computeSquarePaperRange({
    widthPx:1000,heightPx:500,visibleDurationSeconds:2,
    verticalSmallBox:0.1,baseline:0,dataMin:-0.2,dataMax:1.1
  });
  assert.equal(range.canContainData,true);
  assert.ok(range.yMin<=-0.3);
  assert.ok(range.yMax>=1.2);
  assert.equal(range.yMax-range.yMin,2.5);
});
