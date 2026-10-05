export const ECG_PAPER_TIME_SMALL_BOX_S = 0.040;

export function computeSquarePaperRange({
  widthPx,
  heightPx,
  visibleDurationSeconds,
  verticalSmallBox,
  baseline,
  dataMin,
  dataMax,
  marginBoxes = 1
}) {
  for (const [name,value] of Object.entries({
    widthPx,heightPx,visibleDurationSeconds,verticalSmallBox,baseline,dataMin,dataMax
  })) {
    if (!Number.isFinite(Number(value))) throw new Error(name + " must be finite");
  }
  if (widthPx <= 0 || heightPx <= 0 || visibleDurationSeconds <= 0 || verticalSmallBox <= 0) {
    throw new Error("paper geometry dimensions and scales must be positive");
  }

  const smallBoxPx = widthPx * ECG_PAPER_TIME_SMALL_BOX_S / visibleDurationSeconds;
  const verticalBoxCount = heightPx / smallBoxPx;
  const span = verticalBoxCount * verticalSmallBox;
  const margin = Math.max(0, Number(marginBoxes)) * verticalSmallBox;

  let yMin = baseline - span / 2;
  let yMax = baseline + span / 2;

  const requiredMin = Math.min(dataMin, baseline) - margin;
  const requiredMax = Math.max(dataMax, baseline) + margin;
  const requiredSpan = requiredMax - requiredMin;

  if (requiredSpan <= span) {
    if (requiredMin < yMin) {
      const shift = yMin - requiredMin;
      yMin -= shift;
      yMax -= shift;
    }
    if (requiredMax > yMax) {
      const shift = requiredMax - yMax;
      yMin += shift;
      yMax += shift;
    }
  }

  return {
    yMin,
    yMax,
    ySpan: span,
    smallBoxPx,
    verticalBoxCount,
    canContainData: requiredSpan <= span,
    requiredSpan
  };
}

export function pixelsPerVerticalSmallBox({heightPx,yMin,yMax,verticalSmallBox}) {
  return heightPx * verticalSmallBox / (yMax - yMin);
}
