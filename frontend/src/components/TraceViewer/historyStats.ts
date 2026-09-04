export interface ExportHistoryRecord {
  id?: number;
  exporter_name: string;
  unit: string;
  route_name: string;
  export_time: string;
}

export interface DailyExportCount {
  dateKey: string;
  label: string;
  count: number;
}

export interface ExportHistorySummary {
  loadedRecords: number;
  exportsToday: number;
  uniqueRoutes: number;
  maximumDailyCount: number;
  dailyExports: DailyExportCount[];
}

const VIETNAM_TIME_ZONE = 'Asia/Ho_Chi_Minh';
const HISTORY_DAY_COUNT = 7;
const DATE_KEY_PATTERN = /^\d{4}-\d{2}-\d{2}/;

const vietnamDateFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: VIETNAM_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const vietnamDateKey = (date: Date): string => {
  const parts = vietnamDateFormatter.formatToParts(date);
  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}-${values.day}`;
};

const historyDateKey = (value: unknown): string | null => {
  const match = String(value ?? '').trim().match(DATE_KEY_PATTERN);
  return match ? match[0] : null;
};

const previousDateKeys = (todayKey: string): string[] => {
  const [year, month, day] = todayKey.split('-').map(Number);
  return Array.from({ length: HISTORY_DAY_COUNT }, (_, index) => {
    const offset = HISTORY_DAY_COUNT - index - 1;
    return new Date(Date.UTC(year, month - 1, day - offset))
      .toISOString()
      .slice(0, 10);
  });
};

export const summarizeExportHistory = (
  history: ExportHistoryRecord[],
  now: Date = new Date(),
): ExportHistorySummary => {
  const todayKey = vietnamDateKey(now);
  const dateKeys = previousDateKeys(todayKey);
  const counts = new Map(dateKeys.map((dateKey) => [dateKey, 0]));
  const routes = new Set<string>();

  history.forEach((record) => {
    const route = String(record.route_name ?? '').trim().toLocaleLowerCase('vi');
    if (route) routes.add(route);

    const dateKey = historyDateKey(record.export_time);
    if (dateKey && counts.has(dateKey)) {
      counts.set(dateKey, (counts.get(dateKey) ?? 0) + 1);
    }
  });

  const dailyExports = dateKeys.map((dateKey) => ({
    dateKey,
    label: `${dateKey.slice(8, 10)}/${dateKey.slice(5, 7)}`,
    count: counts.get(dateKey) ?? 0,
  }));

  return {
    loadedRecords: history.length,
    exportsToday: counts.get(todayKey) ?? 0,
    uniqueRoutes: routes.size,
    maximumDailyCount: Math.max(0, ...dailyExports.map((item) => item.count)),
    dailyExports,
  };
};
