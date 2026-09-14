// ====== Code Summary ======
// Activity ▸ Trends — the historical/backlog view: hourly created/done/failed/backlog sparklines
// (JobTrendsPanel) plus the live fleet-wide queue depth. Per-stage average duration (`StageDurations`)
// is deliberately NOT here — the backend endpoint (`GET /jobs/stage-durations`) requires a
// `collection_id`, there is no fleet-wide variant; that surface lives on the collection-scoped
// Activity mirror instead (see docforge/app/backend/routers/jobs/router.py).

import { useState } from "react";
import { QueueDepthTile } from "../monitoring/QueueDepthTile";
import { JobTrendsPanel } from "./JobTrendsPanel";

export function ActivityTrendsTab() {
  const [windowHours, setWindowHours] = useState(24);

  return (
    <div>
      <QueueDepthTile />
      <JobTrendsPanel windowHours={windowHours} onWindowHoursChange={setWindowHours} />
    </div>
  );
}
